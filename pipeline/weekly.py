"""GitHub: еженедельная подборка «N фактов недели» из одобренных роликов (релиз videos).
Кладёт подборку в тот же релиз и шлёт в ТГ с ✅/❌ — дальше как обычный ролик."""
import ast, glob, json, os, re, subprocess, sys, time, uuid

W, H, FPS = 1080, 1920, 30
TG_LIMIT_MB = 47
DAYS, MAX = int(os.environ.get("DAYS", 7)), 7
REPO = os.environ["GITHUB_REPOSITORY"]
sys.path.insert(0, os.getcwd())
from app.services import motion  # noqa: E402

FF = motion._ffmpeg()
WORK = os.path.abspath("wk")
os.makedirs(WORK + "/meta", exist_ok=True)
os.makedirs(WORK + "/v", exist_ok=True)


def log(*x):
    print(*x, flush=True)


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-800:])


# ---------- 1. одобренные факты за неделю
approved = set()
if os.path.exists("state/approved.log"):
    approved = {l.strip() for l in open("state/approved.log") if l.strip()}
subprocess.run(["gh", "release", "download", "videos", "-p", "*.json", "-D", WORK + "/meta", "--clobber", "-R", REPO], check=False)
since = time.time() - DAYS * 86400
facts = []
for mf in glob.glob(WORK + "/meta/*.json"):
    try:
        m = json.load(open(mf, encoding="utf-8"))
    except Exception:
        continue
    if m.get("format") != "facts":
        continue
    try:
        t = time.mktime(time.strptime(m.get("created", "")[:19], "%Y-%m-%dT%H:%M:%S"))
    except Exception:
        continue
    if t < since or (approved and m["id"] not in approved):
        continue
    facts.append({"id": m["id"], "topic": m.get("topic", ""), "endcard": True, "t": t})
facts.sort(key=lambda f: f["t"])
facts = facts[-MAX:]
note = "" if approved else "⚠️ Лог одобренных пуст — взял все факты недели, проверь внимательно.\n"
if len(facts) < 3:
    log(f"мало фактов за {DAYS} дн.: {len(facts)} — подборку не делаю")
    sys.exit(0)
for f in facts:
    run(["gh", "release", "download", "videos", "-p", f["id"] + ".mp4", "-D", WORK + "/v", "--clobber", "-R", REPO])
    f["path"] = f"{WORK}/v/{f['id']}.mp4"
N = len(facts)
log(f"фактов: {N}")


# ---------- 2. карточки (размытый кадр + плашка + звук)
def card(bg_video, at, title, sub, dur, out, sound="whoosh"):
    png = out[:-4] + ".png"
    run([FF, "-y", "-v", "error", "-ss", str(at), "-i", bg_video, "-frames:v", "1", png])
    mov = motion._render_frames(motion._endcard_frames(title, sub, dur), out[:-4] + ".mov", motion.ENDCARD_H)
    if sound == "whoosh":
        snd = f"aevalsrc='0.18*sin(2*PI*(220+900*t)*t)*exp(-t*5)':s=44100:d={dur:.2f}"
    else:
        snd = f"aevalsrc='0.22*sin(2*PI*1318*t)*exp(-t*4)+0.14*sin(2*PI*1976*t)*exp(-t*5)':s=44100:d={dur:.2f}"
    run([FF, "-y", "-v", "error", "-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.2f}", "-i", png, "-i", mov,
         "-filter_complex",
         f"[0:v]scale={W}:{H},boxblur=22:2,eq=brightness=-0.25:saturation=1.1,setsar=1[bg];"
         f"[1:v]setpts=PTS-STARTPTS[ov];[bg][ov]overlay=0:{motion.ENDCARD_Y}:eof_action=pass,fps={FPS},format=yuv420p[v];"
         f"{snd},aformat=sample_rates=44100:channel_layouts=stereo[a]",
         "-map", "[v]", "-map", "[a]", "-t", f"{dur:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
         "-c:a", "aac", "-b:a", "160k", out])
    return out


def clip(f, out):
    dur = motion._probe_duration(f["path"])
    if f["endcard"]:
        dur -= motion.ENDCARD_DUR
    run([FF, "-y", "-v", "error", "-i", f["path"], "-t", f"{max(1.0, dur):.2f}",
         "-vf", f"scale={W}:{H},fps={FPS},setsar=1,format=yuv420p", "-af", "aresample=44100,aformat=channel_layouts=stereo",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-b:a", "160k", out])
    return out


stamp = time.strftime("%Y%m%d-%H%M")
wd = os.path.join(WORK, stamp)
os.makedirs(wd, exist_ok=True)
WORD = "ФАКТА" if 2 <= N <= 4 else "ФАКТОВ"
parts = [card(facts[-1]["path"], 3, f"{N} {WORD} НЕДЕЛИ", "от которых мозг скажет «да ладно?!»", 2.6,
              os.path.join(wd, "00_intro.mp4"), "ding")]
for i, f in enumerate(facts):
    num = N - i
    parts.append(card(f["path"], 2, f"#{num}", "", 1.0, os.path.join(wd, f"{i + 1:02d}a_num.mp4")))
    parts.append(clip(f, os.path.join(wd, f"{i + 1:02d}b_clip.mp4")))
    log("готов", num, f["topic"])
parts.append(card(facts[0]["path"], 3, "ПОДПИШИСЬ!", "каждый день новый факт", 2.2, os.path.join(wd, "99_outro.mp4"), "ding"))

# ---------- 3. склейка с битрейтом под лимит Telegram
lst = os.path.join(wd, "list.txt")
open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
total = sum(motion._probe_duration(p) for p in parts)
vbr = max(900, min(4500, int((TG_LIMIT_MB * 8 * 1024 / max(total, 1)) - 140)))
week = int(time.strftime("%V"))
title = f"{N} {WORD.lower()} недели {time.strftime('%d.%m')}"
fid = str(uuid.uuid4())
out = os.path.join(WORK, f"{fid}.mp4")
run([FF, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c:v", "libx264", "-preset", "medium",
     "-b:v", f"{vbr}k", "-maxrate", f"{int(vbr * 1.3)}k", "-bufsize", f"{vbr * 2}k", "-pix_fmt", "yuv420p",
     "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out])
mb = os.path.getsize(out) / 1048576
log(f"подборка: {out} ({total:.0f} c, {mb:.1f} МБ)")

# ---------- 4. в релиз + в ТГ на проверку
meta = {"id": fid, "topic": title, "format": "weekly", "label": "🗓 Подборка", "script": "", "quiz": None,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
json.dump(meta, open(os.path.join(WORK, f"{fid}.json"), "w", encoding="utf-8"), ensure_ascii=False)
run(["gh", "release", "upload", "videos", out, os.path.join(WORK, f"{fid}.json"), "--clobber", "-R", REPO])
import requests
cap = (f"🗓 Подборка: {title} ({total / 60:.1f} мин)\n{note}\n" +
       "\n".join(f"#{N - i}. {f['topic']}" for i, f in enumerate(facts)))[:1000]
kb = {"inline_keyboard": [[{"text": "✅ Постить", "callback_data": "ok:" + fid},
                           {"text": "❌ Удалить", "callback_data": "no:" + fid}]]}
with open(out, "rb") as fh:
    r = requests.post(f"https://api.telegram.org/bot{os.environ['TG_BOT_TOKEN']}/sendVideo",
                      data={"chat_id": os.environ["TG_CHAT_ID"], "caption": cap, "width": W, "height": H,
                            "supports_streaming": "true", "reply_markup": json.dumps(kb)},
                      files={"video": ("weekly.mp4", fh, "video/mp4")}, timeout=600)
log("telegram:", r.status_code, r.text[:200])
