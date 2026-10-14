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

export default {
  // Расписание (Cloudflare Cron Triggers — точнее, чем cron GitHub):
  //   '13 7,12,17 * * *' → генерация: факт / квиз / история
  //   '3 9,15,18 * * *'  → публикация из очереди (12/18/21 МСК)
  //   '7 16,18 * * 0'    → воскресенье: подборка недели (16) и статистика (18)
  async scheduled(event, env, ctx) {
    const h = new Date(event.scheduledTime).getUTCHours();
    if (event.cron.startsWith('13 ')) {
      const f = { 7: 'facts', 12: 'quiz', 17: 'reddit' }[h];
      if (f) ctx.waitUntil(run(env, 'generate.yml', { format: f }));
    } else if (event.cron.startsWith('3 ')) {
      ctx.waitUntil(run(env, 'publish-slot.yml', {}));
    } else if (event.cron.startsWith('7 ')) {
      ctx.waitUntil(run(env, h === 16 ? 'weekly.yml' : 'stats.yml', {}));
    }
  },

  async fetch(req, env, ctx) {
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
        await tg(env, 'sendMessage', { chat_id: m.chat.id, text: 'Команды:\n/fact — факт\n/quiz — квиз\n/story — история\n/now — опубликовать следующий из очереди сразу\n\nВидео с подписью «майнкрафт» или «сатисфай» (можно пачкой) — в фоны для историй.\nВидео на зелёном фоне с подписью «баннер» — баннер на все ролики. «баннер убрать» — убрать.\nФото с подписью «обложка» — шаблон первого слайда каруселей для @obezyanagrustnaya.\n\nРолики по расписанию приходят сами, под ними ✅/❌ (✅ = в очередь на прайм-тайм).' });
      }
    }
    return new Response('ok');
  },
};
