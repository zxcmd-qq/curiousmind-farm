// Curious Mind — бот для кнопок ✅/❌ (Cloudflare Worker, webhook Telegram).
// Секреты: TG_BOT_TOKEN, TG_CHAT_ID, GH_PAT, GH_REPO (например zxcmd-qq/curiousmind-farm), HOOK_SECRET (любая строка)
// Подключение: https://api.telegram.org/bot<TOKEN>/setWebhook?url=<адрес воркера>&secret_token=<HOOK_SECRET>&allowed_updates=["callback_query","message"]

const tg = (env, method, body) => fetch(`https://api.telegram.org/bot${env.TG_BOT_TOKEN}/${method}`, {
  method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) }).then(r => r.json()).catch(() => ({}));

const dispatch = (env, payload) => fetch(`https://api.github.com/repos/${env.GH_REPO}/dispatches`, {
  method: 'POST', body: JSON.stringify({ event_type: 'decision', client_payload: payload }),
  headers: { Authorization: `Bearer ${env.GH_PAT}`, Accept: 'application/vnd.github+json', 'User-Agent': 'curiousmind-bot' } });

const run = (env, workflow, inputs) => fetch(`https://api.github.com/repos/${env.GH_REPO}/actions/workflows/${workflow}/dispatches`, {
  method: 'POST', body: JSON.stringify({ ref: 'main', inputs }),
  headers: { Authorization: `Bearer ${env.GH_PAT}`, Accept: 'application/vnd.github+json', 'User-Agent': 'curiousmind-bot' } });

export default {
  async fetch(req, env) {
    if (req.method !== 'POST') return new Response('ok');
    if (env.HOOK_SECRET && req.headers.get('x-telegram-bot-api-secret-token') !== env.HOOK_SECRET) return new Response('no', { status: 403 });
    const u = await req.json().catch(() => ({}));

    // кнопки ✅/❌ под роликом
    const q = u.callback_query;
    if (q) {
      if (String(q.from?.id) !== String(env.TG_CHAT_ID)) { await tg(env, 'answerCallbackQuery', { callback_query_id: q.id }); return new Response('ok'); }
      const [act, id] = String(q.data || '').split(':');
      if (!['ok', 'no'].includes(act) || !/^[a-f0-9-]{36}$/.test(id || '')) { await tg(env, 'answerCallbackQuery', { callback_query_id: q.id }); return new Response('ok'); }
      const r = await dispatch(env, { id, act });
      const ok = r.status === 204;
      await tg(env, 'answerCallbackQuery', { callback_query_id: q.id,
        text: !ok ? '⚠️ GitHub не ответил: ' + r.status : (act === 'ok' ? '⏳ Публикую на все площадки…' : '🗑 Удалено') });
      if (ok) await tg(env, 'editMessageReplyMarkup', { chat_id: q.message.chat.id, message_id: q.message.message_id,
        reply_markup: { inline_keyboard: [[{ text: act === 'ok' ? '⏳ публикуется…' : '🗑 удалено', callback_data: 'noop:0' }]] } });
      return new Response('ok');
    }

    // команды в личке: /fact /quiz /story — сделать ролик вне расписания
    const m = u.message;
    if (m && String(m.chat?.id) === String(env.TG_CHAT_ID) && typeof m.text === 'string') {
      const map = { '/fact': 'facts', '/quiz': 'quiz', '/story': 'reddit' };
      const f = map[m.text.trim().split(/[ @]/)[0]];
      if (f) {
        const r = await run(env, 'generate.yml', { format: f });
        await tg(env, 'sendMessage', { chat_id: m.chat.id, text: r.status === 204 ? `🎬 Запустил: ${f}. Ролик придёт минут через 10-15.` : `⚠️ GitHub: ${r.status}` });
      } else if (m.text.trim() === '/start' || m.text.trim() === '/help') {
        await tg(env, 'sendMessage', { chat_id: m.chat.id, text: 'Команды:\n/fact — факт\n/quiz — квиз\n/story — история\n\nРолики по расписанию приходят сами, под ними ✅/❌.' });
      }
    }
    return new Response('ok');
  },
};
