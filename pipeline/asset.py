"""GitHub: принимает файл из бота.
asset.py <kind> <file_id> <uid>
kind: minecraft / satisfy → новый фон для историй;  banner → новый баннер (зелёный фон убирается);  nobanner → убрать баннер."""
import json, os, subprocess, sys
import requests
from common import E, log, tg

kind, fid, uid = (sys.argv + ["", "", ""])[1:4]
REPO = E["GITHUB_REPOSITORY"]
NAMES = {"minecraft": "майнкрафт", "satisfy": "сатисфай"}
gh = lambda *a, **k: subprocess.run(["gh", *a, "-R", REPO], capture_output=True, text=True, **k)
say = lambda t: tg("sendMessage", chat=E["TG_CHAT_ID"], text=t)

if gh("release", "view", "assets").returncode != 0:
    gh("release", "create", "assets", "-t", "Фоны", "-n", "Фоны и баннер", "--latest=false")

if kind == "nobanner":
    for f in ("banner.mp4", "banner.json"):
        gh("release", "delete-asset", "assets", f, "-y")
    say("🧹 Баннер убран — новые ролики будут без него.")
    sys.exit(0)

# скачиваем из Telegram (лимит Bot API — 20 МБ)
info = requests.get(f"https://api.telegram.org/bot{E['TG_BOT_TOKEN']}/getFile", params={"file_id": fid}, timeout=30).json()
if not info.get("ok"):
    say(f"⚠️ Не смог скачать файл ({info.get('description', '')}). Боты Telegram берут файлы до 20 МБ — сожми или порежь.")
    sys.exit(0)
src = "in.bin"
open(src, "wb").write(requests.get(f"https://api.telegram.org/file/bot{E['TG_BOT_TOKEN']}/{info['result']['file_path']}", timeout=300).content)
dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src], capture_output=True, text=True).stdout.strip()
if not dur:
    say("⚠️ Это не похоже на видео.")
    sys.exit(0)

if kind in NAMES:
    out = f"bg-{kind}-{uid}.mp4"
    # приводим к вертикали 1080x1920 без звука — как остальные фоны
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src, "-an", "-vf",
                        "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,format=yuv420p",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-movflags", "+faststart", out], capture_output=True, text=True)
    if r.returncode != 0:
        say("⚠️ Не смог обработать видео: " + r.stderr[-200:])
        sys.exit(1)
    gh("release", "upload", "assets", out, "--clobber", check=True)
    have = json.loads(gh("release", "view", "assets", "--json", "assets").stdout or "{}").get("assets", [])
    n = sum(1 for a in have if a["name"].startswith(f"bg-{kind}-"))
    say(f"✅ +1 фон в «{NAMES[kind]}» ({float(dur):.0f} с). Своих фонов там уже: {n}")

elif kind == "banner":
    # цвет фона берём из углов первого кадра (если он зелёный), иначе — чистый зелёный
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-vf", "crop=16:16:0:0,scale=1:1", "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    color = "0x00FF00"
    if len(raw) >= 3 and raw[1] > raw[0] + 40 and raw[1] > raw[2] + 40:
        color = "0x%02X%02X%02X" % (raw[0], raw[1], raw[2])
    meta = {"color": color, "similarity": 0.2, "blend": 0.08, "despill": "green"}
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src, "-an", "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "18", "banner.mp4"], check=True)
    json.dump(meta, open("banner.json", "w"))
    gh("release", "upload", "assets", "banner.mp4", "banner.json", "--clobber", check=True)
    # превью: баннер без зелени поверх серого
    key = f"chromakey={color}:0.2:0.08,despill=type=green,scale=760:260:force_original_aspect_ratio=decrease"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0x30343c:s=900x340", "-i", "banner.mp4", "-filter_complex",
                    f"[1:v]{key}[b];[0:v][b]overlay=(W-w)/2:(H-h)/2", "-frames:v", "1", "preview.png"], check=False)
    cap = f"✅ Новый баннер (фон {color} убран). Будет на всех следующих роликах под субтитрами. Убрать — напиши «баннер убрать»."
    if os.path.exists("preview.png"):
        tg("sendPhoto", chat=E["TG_CHAT_ID"], files={"photo": ("p.png", open("preview.png", "rb"), "image/png")}, caption=cap)
    else:
        say(cap)
