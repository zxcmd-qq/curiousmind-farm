// Curious Mind — бот для кнопок ✅/❌ (Cloudflare Worker, webhook Telegram).
// Секреты: TG_BOT_TOKEN, TG_CHAT_ID, GH_PAT, GH_REPO (например zxcmd-qq/curiousmind-farm), HOOK_SECRET (любая строка)
// Привязка KV с именем KV (для альбомов видео)
// Подключение: setWebhook с allowed_updates=["callback_query","message","channel_post"]
// Необязательно: TT2_CHANNEL — @ник или id ТГК для каруселей (иначе берётся любой канал, кроме @crpstv)

const tg = (env, method, body) => fetch(`https://api.telegram.org/bot${env.TG_BOT_TOKEN}/${method}`, {
  method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) }).then(r => r.json()).catch(() => ({}));

const dispatch = (env, payload) => fetch(`https://api.github.com/repos/${env.GH_REPO}/dispatches`, {
  method: 'POST', body: JSON.stringify({ event_type: 'decision', client_payload: payload }),
  headers: { Authorization: `Bearer ${env.GH_PAT}`, Accept: 'application/vnd.github+json', 'User-Agent': 'curiousmind-bot' } });

const run = (env, workflow, inputs) => fetch(`https://api.github.com/repos/${env.GH_REPO}/actions/workflows/${workflow}/dispatches`, {
  method: 'POST', body: JSON.stringify({ ref: 'main', inputs }),
  headers: { Authorization: `Bearer ${env.GH_PAT}`, Accept: 'application/vnd.github+json', 'User-Agent': 'curiousmind-bot' } });

// ---------- расписание (UTC). Нужен ОДИН Cron Trigger в Cloudflare: 3 * * * *  (каждый час в :03)
// Польша зимой = UTC+1, летом UTC+2; МСК = UTC+3.
const GEN = { 6: 'facts', 9: 'quiz', 12: 'facts', 15: 'reddit' };      // 4 ролика в день
const PUB = [9, 12, 15, 18];                                            // публикация из очереди: 12/15/18/21 МСК
const SUN = { 16: 'weekly.yml', 18: 'stats.yml' };                      // воскресенье: подборка недели, анализ
const FMT = { facts: 'факт', quiz: 'квиз', reddit: 'история' };
const pl = h => String((h + 1) % 24).padStart(2, '0') + ':03';          // для подсказок — зимнее время Польши

const ADAM = 'elevenlabs:pNInz6obpgDQGcFmaJgB:Adam';
const GEMINI = 'gemini:Fenrir-Excitable';
const el = (key, path) => fetch('https://api.elevenlabs.io' + path, { headers: { 'xi-api-key': key } })
  .then(async r => ({ ok: r.ok, status: r.status, j: await r.json().catch(() => ({})) })).catch(e => ({ ok: false, status: 0, j: { e: String(e) } }));
async function elLeft(key) {
  const r = await el(key, '/v1/user/subscription');
  return r.ok ? (r.j.character_limit || 0) - (r.j.character_count || 0) : null;
}
async function elVoices(key) {
  const r = await el(key, '/v2/voices?page_size=50');
  return r.ok ? (r.j.voices || []).map(v => ({ id: v.voice_id, name: v.name })) : null;
}
const voiceName = v => !v ? 'по умолчанию (переменная VOICE в GitHub)' : v.startsWith('elevenlabs:') ? 'ElevenLabs — ' + (v.split(':')[2] || v.split(':')[1]) : v.replace('gemini:', 'Gemini — ');

export default {
  async scheduled(event, env, ctx) {
    const d = new Date(event.scheduledTime), h = d.getUTCHours(), sun = d.getUTCDay() === 0;
    const jobs = [];
    if (GEN[h]) jobs.push(['generate.yml', { format: GEN[h] }]);
    if (PUB.includes(h)) jobs.push(['publish-slot.yml', {}]);
    if (sun && SUN[h]) jobs.push([SUN[h], {}]);
    const done = [];
    for (const [wf, inputs] of jobs) {
      const r = await run(env, wf, inputs);
      done.push(`${wf}:${r.status}`);
      if (r.status !== 204) await tg(env, 'sendMessage', { chat_id: env.TG_CHAT_ID, text: `⚠️ Расписание: ${wf} не запустился, GitHub ответил ${r.status}: ${(await r.text()).slice(0, 200)}` });
    }
    if (env.KV) await env.KV.put('cron:last', JSON.stringify({ t: d.toISOString(), done }));
  },

  async fetch(req, env, ctx) {
    const path = new URL(req.url).pathname;
    if (path === '/cfg') {                                // читает только GitHub (тот же GH_PAT)
      if (!env.GH_PAT || req.headers.get('authorization') !== 'Bearer ' + env.GH_PAT) return new Response('no', { status: 403 });
      const voice = env.KV ? await env.KV.get('voice') : null, elkey = env.KV ? await env.KV.get('elkey') : null;
      return new Response(JSON.stringify({ voice: voice || '', elkey: elkey || '' }), { headers: { 'content-type': 'application/json' } });
    }
    if (req.method !== 'POST') return new Response('ok');
    if (env.HOOK_SECRET && req.headers.get('x-telegram-bot-api-secret-token') !== env.HOOK_SECRET) return new Response('no', { status: 403 });
    const u = await req.json().catch(() => ({}));

    // ---------- посты из второго ТГК → карусель в TikTok @obezyanagrustnaya
    const cp = u.channel_post;
    if (cp) {
      const uname = String(cp.chat?.username || '').toLowerCase();
      if (uname === 'crpstv') return new Response('ok');
      if (env.TT2_CHANNEL && String(cp.chat.id) !== env.TT2_CHANNEL && uname !== env.TT2_CHANNEL.replace('@', '').toLowerCase()) return new Response('ok');
      const ph = cp.photo ? cp.photo[cp.photo.length - 1] : (cp.document && /^image\//.test(cp.document.mime_type || '') ? cp.document : null);
      if (!ph) return new Response('ok');
      const post = `${cp.chat.id}_${cp.media_group_id || cp.message_id}`;
      const send = files => fetch(`https://api.github.com/repos/${env.GH_REPO}/dispatches`, { method: 'POST',
        body: JSON.stringify({ event_type: 'tt2', client_payload: { ...files, post, chan: cp.chat.title || '' } }),
        headers: { Authorization: `Bearer ${env.GH_PAT}`, Accept: 'application/vnd.github+json', 'User-Agent': 'curiousmind-bot' } });
      if (!cp.media_group_id || !env.KV) {
        ctx.waitUntil(send({ files: [ph.file_id], caption: cp.caption || '' }));
        return new Response('ok');
      }
      // альбом: каждое фото приходит отдельно — копим 15 сек, отправляет то, у кого меньший номер
      await env.KV.put(`tt2:${post}:${cp.message_id}`, JSON.stringify({ id: cp.message_id, f: ph.file_id, c: cp.caption || '' }), { expirationTtl: 3600 });
      ctx.waitUntil((async () => {
        await new Promise(r => setTimeout(r, 15000));
        const list = await env.KV.list({ prefix: `tt2:${post}:` });
        const items = (await Promise.all(list.keys.map(k => env.KV.get(k.name, 'json')))).filter(Boolean).sort((a, b) => a.id - b.id);
        if (!items.length || items[0].id !== cp.message_id) return;
        await send({ files: items.map(i => i.f), caption: items.map(i => i.c).find(Boolean) || '' });
      })());
      return new Response('ok');
    }

    // кнопки ✅/❌ под роликом
    const q = u.callback_query;
    if (q) {
      if (String(q.from?.id) !== String(env.TG_CHAT_ID)) { await tg(env, 'answerCallbackQuery', { callback_query_id: q.id }); return new Response('ok'); }
      if (String(q.data || '').startsWith('v:')) {
        const [, vid, ...nm] = String(q.data).split(':');
        const v = vid === 'gem' ? GEMINI : vid === 'def' ? '' : `elevenlabs:${vid}:${nm.join(':') || vid}`;
        if (v) await env.KV.put('voice', v); else await env.KV.delete('voice');
        await tg(env, 'answerCallbackQuery', { callback_query_id: q.id, text: '🎙 Голос: ' + voiceName(v) });
        await tg(env, 'sendMessage', { chat_id: q.message.chat.id, text: '🎙 Теперь голос: ' + voiceName(v) + '\nПрименится к следующему ролику.' });
        return new Response('ok');
      }
      const [act, id] = String(q.data || '').split(':');
      if (!['ok', 'no'].includes(act) || !/^[a-f0-9-]{36}$/.test(id || '')) { await tg(env, 'answerCallbackQuery', { callback_query_id: q.id }); return new Response('ok'); }
      const r = await dispatch(env, { id, act });
      const ok = r.status === 204;
      await tg(env, 'answerCallbackQuery', { callback_query_id: q.id,
        text: !ok ? '⚠️ GitHub не ответил: ' + r.status : (act === 'ok' ? '⏰ Ставлю в очередь на прайм-тайм' : '🗑 Удалено') });
      if (ok) await tg(env, 'editMessageReplyMarkup', { chat_id: q.message.chat.id, message_id: q.message.message_id,
        reply_markup: { inline_keyboard: [[{ text: act === 'ok' ? '⏰ в очереди' : '🗑 удалено', callback_data: 'noop:0' }]] } });
      return new Response('ok');
    }

    const m = u.message;
    if (!m || String(m.chat?.id) !== String(env.TG_CHAT_ID)) return new Response('ok');

    // фото с подписью «обложка» → шаблон первого слайда каруселей
    if (m.photo && /обложк|cover/i.test(m.caption || '')) {
      const ph = m.photo[m.photo.length - 1];
      const r = await fetch(`https://api.github.com/repos/${env.GH_REPO}/dispatches`, { method: 'POST',
        body: JSON.stringify({ event_type: 'asset', client_payload: { kind: 'tt2cover', file_id: ph.file_id, uid: ph.file_unique_id } }),
        headers: { Authorization: `Bearer ${env.GH_PAT}`, Accept: 'application/vnd.github+json', 'User-Agent': 'curiousmind-bot' } });
      if (r.status !== 204) await tg(env, 'sendMessage', { chat_id: m.chat.id, text: '⚠️ GitHub: ' + r.status });
      return new Response('ok');
    }

    // видео из SnippetFarm: подпись «майнкрафт» / «сатисфай» → в фоны, «баннер» → новый баннер
    const file = m.video || m.animation || (m.document && /^video\//.test(m.document.mime_type || '') ? m.document : null);
    if (file) {
      const cap = String(m.caption || '').toLowerCase();
      let kind = /баннер|banner/.test(cap) ? 'banner' : /майн|minecraft/.test(cap) ? 'minecraft' : /сатисф|satisf|мыло|ковр/.test(cap) ? 'satisfy' : '';
      const mg = m.media_group_id ? `mg:${m.media_group_id}` : '';
      if (kind && mg && env.KV) await env.KV.put(mg, kind, { expirationTtl: 3600 });
      if (!kind && mg && env.KV) {                        // в альбоме подпись только у одного видео — ждём её
        for (let i = 0; i < 8 && !kind; i++) { kind = (await env.KV.get(mg)) || ''; if (!kind) await new Promise(r => setTimeout(r, 1000)); }
      }
      if (!kind) { await tg(env, 'sendMessage', { chat_id: m.chat.id, reply_to_message_id: m.message_id, text: 'Подпиши видео: майнкрафт / сатисфай / баннер' }); return new Response('ok'); }
      if ((file.file_size || 0) > 20 * 1024 * 1024) {
        await tg(env, 'sendMessage', { chat_id: m.chat.id, reply_to_message_id: m.message_id, text: '⚠️ Файл больше 20 МБ — Telegram не даст боту его скачать. Сожми или порежь.' });
        return new Response('ok');
      }
      const r = await fetch(`https://api.github.com/repos/${env.GH_REPO}/dispatches`, { method: 'POST',
        body: JSON.stringify({ event_type: 'asset', client_payload: { kind, file_id: file.file_id, uid: file.file_unique_id } }),
        headers: { Authorization: `Bearer ${env.GH_PAT}`, Accept: 'application/vnd.github+json', 'User-Agent': 'curiousmind-bot' } });
      if (r.status !== 204) await tg(env, 'sendMessage', { chat_id: m.chat.id, text: '⚠️ GitHub: ' + r.status });
      return new Response('ok');
    }

    if (typeof m.text === 'string' && /^баннер (убрать|удалить)|^\/nobanner/i.test(m.text.trim())) {
      await fetch(`https://api.github.com/repos/${env.GH_REPO}/dispatches`, { method: 'POST',
        body: JSON.stringify({ event_type: 'asset', client_payload: { kind: 'nobanner', file_id: '', uid: '' } }),
        headers: { Authorization: `Bearer ${env.GH_PAT}`, Accept: 'application/vnd.github+json', 'User-Agent': 'curiousmind-bot' } });
      return new Response('ok');
    }

    // команды: /fact /quiz /story — ролик вне расписания, /now — опубликовать следующий из очереди сейчас
    if (typeof m.text === 'string') {
      const t = m.text.trim(), cmd = t.split(/[ @]/)[0].toLowerCase(), arg = t.split(/\s+/).slice(1).join(' ').trim();
      const say = text => tg(env, 'sendMessage', { chat_id: m.chat.id, text, disable_web_page_preview: true });
      if (cmd === '/stats' || cmd === '/weekly') {
        const r = await run(env, cmd === '/stats' ? 'stats.yml' : 'weekly.yml', {});
        await say(r.status === 204 ? (cmd === '/stats' ? '📊 Запустил анализ статистики, отчёт придёт минут через 3-5.' : '🎞 Запустил подборку недели, придёт минут через 15-20.') : `⚠️ GitHub: ${r.status}`);
        return new Response('ok');
      }
      if (cmd === '/status') {
        const last = env.KV ? await env.KV.get('cron:last', 'json') : null;
        const key = env.KV ? await env.KV.get('elkey') : null, v = env.KV ? await env.KV.get('voice') : null;
        const left = key ? await elLeft(key) : null;
        await say('🕒 Расписание (время Польши, зимнее):\n' +
          Object.entries(GEN).map(([h, f]) => `  ${pl(+h)} — ${FMT[f]}`).join('\n') +
          '\nПубликация: ' + PUB.map(pl).join(', ') + ' (из очереди ✅)\nВоскресенье: ' + pl(16) + ' подборка недели, ' + pl(18) + ' анализ\n\n' +
          (last ? `Последний запуск по расписанию: ${new Date(last.t).toLocaleString('ru-RU', { timeZone: 'Europe/Warsaw' })}${last.done.length ? ' → ' + last.done.join(', ') : ' (в этот час задач нет)'}` :
            '❌ Расписание ещё ни разу не срабатывало — проверь Cron Trigger «3 * * * *» у cm-bot в Cloudflare.') +
          `\n\n🎙 Голос: ${voiceName(v)}` + (key ? `\nElevenLabs: ${left == null ? 'ключ есть (остаток не видно — у ключа нет права user_read)' : 'осталось ' + left + ' символов (~' + Math.floor(left / 600) + ' роликов)'}` : '\nElevenLabs: ключа нет'));
        return new Response('ok');
      }
      if (cmd === '/elkey') {
        await tg(env, 'deleteMessage', { chat_id: m.chat.id, message_id: m.message_id });   // ключ не висит в чате
        if (!arg) { await say('Пришли так: /elkey ключ_от_ElevenLabs\n(сообщение с ключом я сразу удалю)\n\n/elkey удалить — убрать ключ'); return new Response('ok'); }
        if (/^(удалить|delete|off)$/i.test(arg)) { await env.KV.delete('elkey'); await say('🗑 Ключ ElevenLabs удалён. Пока он не нужен — озвучка будет Gemini.'); return new Response('ok'); }
        const left = await elLeft(arg), voices = await elVoices(arg);
        if (left == null && voices == null) { await say('❌ ElevenLabs не принял ключ. Проверь, что скопирован целиком (и что у ключа включён доступ к Text to Speech).'); return new Response('ok'); }
        await env.KV.put('elkey', arg);
        const cur = await env.KV.get('voice');
        await say('✅ Ключ ElevenLabs сохранён.' + (left != null ? ` Осталось ${left} символов (~${Math.floor(left / 600)} роликов).` : '') +
          (cur && cur.startsWith('elevenlabs:') ? '' : '\n\nВключить голос: /voice adam (или /voices — выбрать из списка)'));
        return new Response('ok');
      }
      if (cmd === '/voices') {
        const key = await env.KV.get('elkey');
        if (!key) { await say('Сначала ключ: /elkey ключ'); return new Response('ok'); }
        const vs = await elVoices(key);
        if (!vs) { await say('Не смог получить список (у ключа нет права voices_read). Можно так: /voice adam или /voice elevenlabs:ID_голоса:Имя'); return new Response('ok'); }
        const rows = vs.slice(0, 40).map(v => [{ text: v.name.slice(0, 40), callback_data: `v:${v.id}:${v.name.replace(/[^\wА-Яа-яЁё ]/g, '').slice(0, 30)}`.slice(0, 64) }]);
        rows.push([{ text: 'Gemini Fenrir (бесплатно)', callback_data: 'v:gem' }, { text: 'По умолчанию', callback_data: 'v:def' }]);
        await tg(env, 'sendMessage', { chat_id: m.chat.id, text: '🎙 Выбери голос:', reply_markup: { inline_keyboard: rows } });
        return new Response('ok');
      }
      if (cmd === '/voice') {
        const cur = await env.KV.get('voice');
        if (!arg) {
          await tg(env, 'sendMessage', { chat_id: m.chat.id, text: `🎙 Сейчас: ${voiceName(cur)}\n\n/voice adam — Adam (ElevenLabs)\n/voice gemini — Gemini Fenrir\n/voice gemini:Puck-Upbeat — другой голос Gemini\n/voices — все голоса ElevenLabs\n/elkey ключ — новый ключ ElevenLabs`,
            reply_markup: { inline_keyboard: [[{ text: 'Adam (ElevenLabs)', callback_data: 'v:pNInz6obpgDQGcFmaJgB:Adam' }, { text: 'Gemini Fenrir', callback_data: 'v:gem' }]] } });
          return new Response('ok');
        }
        let v = null;
        if (/^adam$/i.test(arg)) v = ADAM;
        else if (/^gemini$/i.test(arg)) v = GEMINI;
        else if (/^(gemini|elevenlabs):/i.test(arg)) v = arg;
        else {
          const key = await env.KV.get('elkey'), vs = key ? await elVoices(key) : null;
          const f = (vs || []).find(x => x.name.toLowerCase().startsWith(arg.toLowerCase()));
          if (f) v = `elevenlabs:${f.id}:${f.name}`;
        }
        if (!v) { await say('Не нашёл такой голос. Список: /voices'); return new Response('ok'); }
        await env.KV.put('voice', v);
        await say('🎙 Теперь голос: ' + voiceName(v) + (v.startsWith('elevenlabs:') && !(await env.KV.get('elkey')) ? '\n⚠️ Ключа ElevenLabs нет — пришли /elkey ключ, иначе будет Gemini.' : '\nПрименится к следующему ролику.'));
        return new Response('ok');
      }
      if (m.text.trim().startsWith('/now')) {
        const r = await run(env, 'publish-slot.yml', {});
        await tg(env, 'sendMessage', { chat_id: m.chat.id, text: r.status === 204 ? '🚀 Публикую следующий из очереди.' : `⚠️ GitHub: ${r.status}` });
        return new Response('ok');
      }
      const map = { '/fact': 'facts', '/quiz': 'quiz', '/story': 'reddit' };
      const f = map[m.text.trim().split(/[ @]/)[0]];
      if (f) {
        const r = await run(env, 'generate.yml', { format: f });
        await tg(env, 'sendMessage', { chat_id: m.chat.id, text: r.status === 204 ? `🎬 Запустил: ${f}. Ролик придёт минут через 10-15.` : `⚠️ GitHub: ${r.status}` });
      } else if (m.text.trim() === '/start' || m.text.trim() === '/help') {
        await tg(env, 'sendMessage', { chat_id: m.chat.id, text: 'Команды:\n/fact — факт\n/quiz — квиз\n/story — история\n/now — опубликовать следующий из очереди сразу\n/stats — анализ статистики сейчас\n/weekly — подборка недели сейчас\n/status — расписание, голос, остаток ElevenLabs\n/voice — сменить голос, /voices — список ElevenLabs\n/elkey ключ — ключ ElevenLabs\n\nВидео с подписью «майнкрафт» или «сатисфай» (можно пачкой) — в фоны для историй.\nВидео на зелёном фоне с подписью «баннер» — баннер на все ролики. «баннер убрать» — убрать.\nФото с подписью «обложка» — шаблон первого слайда каруселей для @obezyanagrustnaya.\n\nРолики по расписанию приходят сами, под ними ✅/❌ (✅ = в очередь на прайм-тайм).' });
      }
    }
    return new Response('ok');
  },
};
