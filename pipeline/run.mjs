// Curious Mind — генерация одного ролика на GitHub Actions.
// Логика сценариев — те же JS-ноды, что в n8n (pipeline/nodes/*.js), тут только «клей».
import fs from 'node:fs';
import { execFileSync } from 'node:child_process';

const env = process.env;
const ST = 'state';
const MPT = 'http://127.0.0.1:8080';
const REPO = env.GITHUB_REPOSITORY;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const read = (f, d = '') => { try { return fs.readFileSync(f, 'utf8'); } catch { return d; } };
const append = (f, s) => fs.appendFileSync(f, s.endsWith('\n') ? s : s + '\n');
const log = (...a) => console.log('▶', ...a);

const out = {};
const $ = name => ({ first: () => ({ json: out[name] }), item: { json: out[name] }, all: () => [{ json: out[name] }] });
function node(file, $json) {
  const code = fs.readFileSync(`pipeline/nodes/${file}.js`, 'utf8');
  return new Function('$', '$json', code)($, $json)[0].json;
}

async function tg(method, body, isForm = false) {
  const r = await fetch(`https://api.telegram.org/bot${env.TG_BOT_TOKEN}/${method}`,
    isForm ? { method: 'POST', body } : { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (!j.ok) log('telegram:', method, JSON.stringify(j).slice(0, 300));
  return j;
}

async function main() {
  // 1. Settings
  out['Settings'] = { TG_BOT_TOKEN: env.TG_BOT_TOKEN, TG_CHAT_ID: env.TG_CHAT_ID, MPT, FORCE_FORMAT: env.FORMAT || '',
    VOICE: env.CM_VOICE || env.VOICE || 'gemini:Fenrir-Excitable', trigger: 'make' };

  // 2. Read Used + insights → Pick Format
  const used = read(`${ST}/used-facts.txt`).split('\n').slice(-300).join('\n');
  out['Read Used'] = { stdout: used + "\n@@INSIGHTS@@\n" + read(`${ST}/insights.json`, '{}') };
  out['Pick Format'] = node('Pick_Format', out['Read Used']);
  const format = out['Pick Format'].format;
  log('format:', format, '| cat:', out['Pick Format'].cat);

  // 3. Get Reddit (Пикабу или часть 2 сериала)
  let stdout = '{}';
  if (format === 'reddit') {
    const q = `${ST}/series-queue.json`;
    if (read(q).trim()) { stdout = read(q); fs.renameSync(q, `${ST}/series-queue.used.json`); log('сериал: часть 2'); }
    else {
      try { stdout = execFileSync('python', ['pipeline/pikabu_fetch.py'], { env: { ...env, CM_STATE: ST }, encoding: 'utf8', timeout: 180000 }); }
      catch (e) { log('pikabu fail:', String(e.stderr || e).slice(0, 300)); }
    }
  }
  out['Get Reddit'] = { stdout };

  // 4. Build Prompt → Gemini → Build Task
  async function askGemini(prompt) {
    let gem = {};
    for (let attempt = 1; attempt <= 4; attempt++) {   // Gemini иногда отвечает 429/503 — ждём и пробуем ещё
      gem = await fetch('https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent', {
        method: 'POST', headers: { 'content-type': 'application/json', 'x-goog-api-key': env.GEMINI_KEY },
        body: JSON.stringify({ generationConfig: { responseMimeType: 'application/json', temperature: 1.0 },
          contents: [{ parts: [{ text: prompt }] }] }) }).then(r => r.json()).catch(e => ({ error: { message: String(e) } }));
      if (gem.candidates?.[0]?.content?.parts?.[0]?.text || gem.promptFeedback?.blockReason || gem.candidates?.[0]?.finishReason) break;
      log(`Gemini попытка ${attempt}:`, JSON.stringify(gem).slice(0, 400));
      if (attempt < 4) await sleep(30000 * attempt);
    }
    if (gem.error) throw new Error('Gemini: ' + (gem.error.message || JSON.stringify(gem.error)).slice(0, 250));
    return gem;
  }

  // истории — парами по рейтингу: если Gemini блокирует пару, выкидываем только её и пробуем следующую
  let rr = {};
  try { rr = JSON.parse(out['Get Reddit'].stdout || '{}'); } catch {}
  const pool = (rr.stories || []).slice().sort((a, b) => (b.rating || 0) - (a.rating || 0));
  const packs = format === 'reddit' && !rr.part2 && pool.length ? [] : [null];
  for (let i = 0; i < pool.length && packs.length < 5; i += 2) packs.push(pool.slice(i, i + 2));
  let bt, blockedIds = [];
  for (const pack of packs) {
    if (pack) out['Get Reddit'] = { stdout: JSON.stringify({ ...rr, stories: pack }) };
    out['Build Prompt'] = node('Build_Prompt');
    log('prompt:', out['Build Prompt'].format, '| историй:', (out['Build Prompt'].stories || []).length, '| символов:', out['Build Prompt'].prompt.length);
    const gem = await askGemini(out['Build Prompt'].prompt);
    out['Script (Gemini)'] = gem;
    bt = node('Build_Task', gem);
    if (!bt.blocked) break;
    log('заблокировано:', bt.blocked, JSON.stringify(gem.promptFeedback || gem.candidates?.[0]?.safetyRatings || '').slice(0, 300));
    blockedIds.push(...(bt.redditIds || []));
  }
  out['Build Task'] = bt;

  // 4b. Анти-повтор: Gemini сверяет СУТЬ нового ролика с прошлыми темами (заголовки бывают разные, а предмет тот же)
  const pastTopics = read(`${ST}/used-facts.txt`).split('\n').map(s => s.trim()).filter(s => s && !/^(reddit|pikabu):/.test(s)).slice(-400);
  let subject = '';
  if (!bt.blocked && format !== 'reddit' && pastTopics.length) {
    for (let tryN = 0; tryN < 3; tryN++) {
      let chk = {};
      try {
        const g = await askGemini(`Новый ролик. Заголовок: «${bt.topic}». Озвучка: «${bt.script}»\n\nПрошлые ролики (заголовок, иногда [суть]):\n${pastTopics.join('\n')}\n\n` +
          'Определи СУТЬ нового ролика в 2-4 словах — главный предмет или факт (например «гребля калории», «жвачка в СССР»). ' +
          'Потом проверь: был ли уже ролик ПРО ТО ЖЕ САМОЕ — тот же предмет или тот же факт, даже если заголовок другой? Просто общая область (например «животные», «космос») — не повтор. ' +
          'Ответь ТОЛЬКО JSON: {"subject": "...", "dup": true или false, "same_as": "какой прошлый ролик или пусто"}');
        chk = JSON.parse((g.candidates?.[0]?.content?.parts?.[0]?.text || '').match(/\{[\s\S]*\}/)[0]);
      } catch (e) { log('проверка повторов не удалась:', String(e).slice(0, 200)); break; }
      subject = String(chk.subject || '').replace(/[\[\]\n`$\\"]/g, '').trim().slice(0, 40);
      if (!chk.dup || tryN === 2) { log(chk.dup ? 'всё ещё похоже, оставляю:' : 'повтора нет, суть:', subject); break; }
      log(`повтор ${tryN + 1}: «${subject}» уже было («${chk.same_as}») → беру другую тему`);
      out['Build Prompt'].prompt += `\nВАЖНО: тема «${subject}» уже была («${String(chk.same_as || '').slice(0, 80)}»). Возьми СОВСЕМ другой предмет.`;
      const gem = await askGemini(out['Build Prompt'].prompt);
      const nb = node('Build_Task', gem);
      if (nb.blocked) break;
      out['Script (Gemini)'] = gem; bt = nb; out['Build Task'] = bt;
    }
  }

  // 5. Remember
  for (const id of blockedIds) append(`${ST}/used-facts.txt`, 'pikabu:' + id);
  if (bt.blocked) {
    await tg('sendMessage', { chat_id: env.TG_CHAT_ID, text: `⚠️ Gemini заблокировал все ${blockedIds.length} историй с Пикабу (${bt.blocked}). Выкинул их, в следующий раз будут другие.` });
    return;
  }
  if (blockedIds.length) log('выкинуто заблокированных историй:', blockedIds.length);
  if (bt.topic) append(`${ST}/used-facts.txt`, String(bt.topic).replace(/[`$\\"]/g, '') + (subject ? ` [суть: ${subject}]` : ''));
  if (bt.redditId) append(`${ST}/used-facts.txt`, 'pikabu:' + bt.redditId);
  if (bt.queueB64) fs.writeFileSync(`${ST}/series-queue.json`, Buffer.from(bt.queueB64, 'base64').toString('utf8'));

  // 5b. Проверка крючка: первая фраза решает, листать или смотреть
  if (bt.script && !/^Вторая часть/i.test(bt.script)) {
    try {
      const h = await askGemini(`Ты продюсер вирусных Shorts/TikTok. Вот сценарий озвучки:\n«${bt.script}»\n\n` +
        'Оцени КРЮЧОК — первую фразу — от 1 до 10: насколько сильно она заставляет досмотреть (интрига, конкретика, неожиданность в первые 2 секунды). ' +
        'Если оценка ниже 8 — перепиши ТОЛЬКО первую фразу (до 15 слов), чтобы цепляла сильнее: тот же разговорный стиль (мат можно), без слов «жесть/шок/ужас», ' +
        'без выдуманных фактов, она должна логично вести к следующей фразе сценария. Ответь ТОЛЬКО JSON: {"score": число, "hook": "новая первая фраза или пустая строка, если 8+"}');
      const txt = h.candidates?.[0]?.content?.parts?.[0]?.text || '';
      const r = JSON.parse(txt.match(/\{[\s\S]*\}/)[0]);
      const m = bt.script.match(/^[\s\S]*?[.!?…]+(?=\s|$)/);
      log('крючок:', r.score, r.hook ? '→ переписан' : '');
      if (Number(r.score) < 8 && r.hook && m && r.hook.length < 200) {
        bt.script = String(r.hook).trim() + bt.script.slice(m[0].length);
        bt.body.video_script = bt.script;
      }
    } catch (e) { log('проверка крючка пропущена:', String(e).slice(0, 150)); }
  }

  // 6. MoneyPrinterTurbo
  const cr = await fetch(`${MPT}/api/v1/videos`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(bt.body) }).then(r => r.json());
  const taskId = cr?.data?.task_id;
  if (!taskId) throw new Error('MPT не принял задачу: ' + JSON.stringify(cr).slice(0, 300));
  log('task', taskId);
  let state = 0;
  for (let i = 0; i < 160 && state !== 1; i++) {
    await sleep(15000);
    const t = await fetch(`${MPT}/api/v1/tasks/${taskId}`).then(r => r.json()).catch(() => ({}));
    state = t?.data?.state;
    if (state === -1) throw new Error('MPT: задача упала, смотри mpt.log');
    if (i % 4 === 0) log('progress', t?.data?.progress);
  }
  const video = `storage/tasks/${taskId}/final-1.mp4`;
  if (state !== 1 || !fs.existsSync(video)) throw new Error('видео не готово');

  // 6b. Баннер (если загружен через бота): убираем зелёный фон и кладём в свободную зону под субтитрами
  let finalVideo = video;
  try {
    fs.mkdirSync('banner', { recursive: true });
    execFileSync('gh', ['release', 'download', 'assets', '-p', 'banner.mp4', '-p', 'banner.json', '-D', 'banner', '--clobber', '-R', REPO], { stdio: 'pipe' });
    if (fs.existsSync('banner/banner.mp4')) {
      const b = JSON.parse(read('banner/banner.json', '{}'));
      const key = `chromakey=${b.color || '0x00FF00'}:${b.similarity || 0.2}:${b.blend || 0.08},despill=type=${b.despill || 'green'}`;
      execFileSync('ffmpeg', ['-y', '-v', 'error', '-i', video, '-stream_loop', '-1', '-i', 'banner/banner.mp4', '-filter_complex',
        `[1:v]${key},scale=760:260:force_original_aspect_ratio=decrease,format=yuva420p[b];[0:v][b]overlay=(W-w)/2:1160+(260-h)/2:shortest=1[v]`,
        '-map', '[v]', '-map', '0:a', '-c:v', 'libx264', '-preset', 'medium', '-crf', '22', '-maxrate', '8M', '-bufsize', '16M',
        '-pix_fmt', 'yuv420p', '-c:a', 'copy', '-movflags', '+faststart', 'bannered.mp4'], { stdio: 'pipe' });
      finalVideo = 'bannered.mp4';
      log('баннер наложен');
    }
  } catch (e) { log('без баннера:', String(e.stderr || e).slice(0, 200)); }

  // 7. Видео + описание → релиз «videos» (оттуда Мак его скачает после ✅)
  const meta = { id: taskId, topic: bt.topic, format: bt.format, label: bt.label, script: bt.script,
    quiz: bt.quizB64 ? JSON.parse(Buffer.from(bt.quizB64, 'base64').toString('utf8')) : null, created: new Date().toISOString() };
  fs.writeFileSync(`${taskId}.json`, JSON.stringify(meta, null, 1));
  fs.copyFileSync(finalVideo, `${taskId}.mp4`);
  execFileSync('gh', ['release', 'upload', 'videos', `${taskId}.mp4`, `${taskId}.json`, '--clobber', '-R', REPO], { stdio: 'inherit' });

  // 8. Тебе в ТГ на проверку
  const fd = new FormData();
  fd.append('chat_id', env.TG_CHAT_ID);
  fd.append('caption', (bt.label + ': ' + bt.topic + '\n\nТекст озвучки:\n' + bt.script).slice(0, 1000));
  fd.append('width', '1080'); fd.append('height', '1920'); fd.append('supports_streaming', 'true');
  fd.append('reply_markup', JSON.stringify({ inline_keyboard: [[{ text: '✅ Постить', callback_data: 'ok:' + taskId }, { text: '❌ Удалить', callback_data: 'no:' + taskId }]] }));
  fd.append('video', new Blob([fs.readFileSync(finalVideo)], { type: 'video/mp4' }), 'video.mp4');
  await tg('sendVideo', fd, true);
  log('готово:', bt.label, bt.topic);
}

main().catch(async e => {
  console.error(e);
  await tg('sendMessage', { chat_id: env.TG_CHAT_ID, text: '❌ GitHub-генерация упала: ' + String(e.message || e).slice(0, 300) + `\nhttps://github.com/${REPO}/actions` }).catch(() => {});
  process.exit(1);
});
