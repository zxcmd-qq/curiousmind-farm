const cfg = $('Settings').first().json;
const [usedRaw, insRaw] = String($json.stdout || '').split('@@INSIGHTS@@');
let ins = {};
try { ins = JSON.parse(String(insRaw || '').trim() || '{}'); } catch (e) {}
const used = String(usedRaw || '').split('\n').map(s => s.trim()).filter(Boolean);
const h = Number(new Date().toLocaleString('en-US', { timeZone: 'Europe/Warsaw', hour: 'numeric', hour12: false }));
const SLOTS = { 9: 'facts', 14: 'quiz', 19: 'reddit' };
const ALL = ['facts', 'quiz', 'reddit'];
let format = cfg.FORCE_FORMAT || SLOTS[h] || ALL[Math.floor(Math.random() * ALL.length)];
if (!ALL.includes(format)) format = 'facts';   // звук выпилен
const pick = a => a[Math.floor(Math.random() * a.length)];
const CATS = ['человеческое тело и мозг', 'животные и их странные способности', 'космос и планеты', 'океан и глубоководные существа',
  'история: странные случаи и забытые события', 'древние цивилизации', 'психология и поведение людей',
  'еда и как она делается на самом деле', 'технологии и изобретения', 'деньги, бренды и бизнес-истории',
  'природные явления и катастрофы', 'преступления и аферы прошлого (без жестокости)', 'спорт и рекорды',
  'языки, слова и их происхождение', 'физика и химия в повседневной жизни', 'насекомые и микробы',
  'география: странные места на Земле', 'сон и сновидения', 'кино и игры: факты со съёмок'];
const SOUND_CATS = ['космос (настоящие записи NASA: планеты, Солнце, кометы, зонды)', 'животные (киты, птицы, насекомые, необычные крики)',
  'природа (вулканы, ледники, землетрясения, гром)', 'история и техника (первые записи голоса, старые машины, ракеты, сирены)',
  'необычные музыкальные инструменты'];
const SUBS = ['tifu', 'MaliciousCompliance', 'pettyrevenge', 'AmItheAsshole', 'TrueOffMyChest', 'confession', 'ProRevenge', 'entitledparents'];
// темы, которые зашли по статистике, выпадают чаще
const wpick = a => { const w = a.map(x => Math.max(0.2, Number((ins.cat_weights || {})[x]) || 1));
  let r = Math.random() * w.reduce((s, v) => s + v, 0);
  for (let i = 0; i < a.length; i++) { r -= w[i]; if (r <= 0) return a[i]; } return a[a.length - 1]; };
const cat = format === 'sound' ? pick(SOUND_CATS) : wpick(CATS);
return [{ json: { format, cat, sub: pick(SUBS), used, ins } }];