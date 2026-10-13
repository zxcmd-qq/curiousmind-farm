const cfg = $('Settings').first().json;
const bp = $('Build Prompt').first().json;
const txt = $json.candidates?.[0]?.content?.parts?.[0]?.text || '';
const blocked = $json.promptFeedback?.blockReason || (!txt && $json.candidates?.[0]?.finishReason);
if (blocked) {
  if (bp.format === 'reddit' && !bp.series)   // одна из историй запрещённая — выкидываем всю пачку
    return [{ json: { blocked: String(blocked), topic: '', format: bp.format, redditIds: (bp.stories || []).map(s => s.id) } }];
  throw new Error('Gemini заблокировал запрос (' + blocked + ') — запусти ещё раз');
}
let r;
try { r = JSON.parse(txt.match(/\{[\s\S]*\}/)[0]); } catch (e) { throw new Error('Gemini вернул не JSON: ' + txt.slice(0, 300)); }
if (bp.series) r = { topic: bp.series.topic, script: bp.series.script };
let topic = String(r.topic || 'Интересное').replace(/[\\/:*?"<>|\n\r\t]+/g, ' ').trim().slice(0, 90);
const body = {
  video_subject: topic, video_script: String(r.script || ''), video_terms: (r.terms || ['abstract background']).slice(0, 5),
  video_aspect: '9:16', video_source: 'wiki', wiki_terms: (r.wiki || []).slice(0, 3), video_concat_mode: 'random',
  video_clip_duration: 3, video_count: 1, video_language: 'ru-RU', voice_name: cfg.VOICE, voice_rate: 1.1, voice_volume: 1.0,
  bgm_type: 'random', bgm_volume: 0.2, subtitle_enabled: true, subtitle_position: 'center',
  subtitle_display_mode: 'word_by_word', subtitle_animation: 'pop_spring', font_name: 'bangerscyrillic.ttf',
  font_size: 75, text_fore_color: '#FFFFFF', stroke_color: '#000000', stroke_width: 4, autopost: false,
};
let redditId = '';
let quizB64 = '';
let queueB64 = '';
if (bp.format === 'facts') body.callouts = (r.callouts || []).slice(0, 4);
if (bp.format === 'quiz') { body.quiz = { options: (r.options || []).slice(0, 3), answer: Number(r.answer) || 0 }; body.callouts = [];
  const qz = JSON.stringify({ topic, options: body.quiz.options, answer: body.quiz.answer, explain: String(r.explain || '').slice(0, 190) });
  quizB64 = (typeof Buffer !== 'undefined' ? Buffer.from(qz).toString('base64') : btoa(unescape(encodeURIComponent(qz)))); }
if (bp.format === 'reddit') {
  const s = bp.series ? { id: bp.series.id, author: bp.series.author } : (bp.stories[(parseInt(r.index) || 1) - 1] || bp.stories[0]);
  redditId = s ? s.id : '';
  const part2 = bp.series ? '' : String(r.part2 || '').trim();
  if (part2.length > 200) {   // сериал: часть 2 выйдет в следующем слоте историй
    const q = JSON.stringify({ part2: true, topic: ('Часть 2. ' + topic).slice(0, 95), script: part2, id: redditId, author: (s && s.author) || '' });
    queueB64 = typeof Buffer !== 'undefined' ? Buffer.from(q).toString('base64') : btoa(unescape(encodeURIComponent(q)));
    topic = ('Часть 1. ' + topic).slice(0, 95);
    body.video_subject = topic;
    body.endcard = { title: 'ЧАСТЬ 2 ЗАВТРА!', sub: 'подпишись, чтобы не пропустить' };
  } else body.endcard = { title: 'ПОДПИШИСЬ!', sub: 'новая история каждый день' };
  Object.assign(body, { video_source: 'gameplay', video_clip_duration: 12, title_style: 'pikabu', reddit_sub: (s && s.author) || '', bgm_volume: 0.12 });
}
if (bp.format === 'facts') body.endcard = { title: 'ПОДПИШИСЬ!', sub: 'каждый день новый факт' };
if (bp.format === 'quiz') body.endcard = { title: 'ПОДПИШИСЬ!', sub: 'завтра новый квиз' };
const LABEL = { facts: '💡 Факт', quiz: '❓ Квиз', reddit: '📖 История (Пикабу)', sound: '🔊 Звук' }[bp.format];
return [{ json: { body, topic, script: body.video_script, format: bp.format, label: LABEL, redditId, queueB64, quizB64 } }];