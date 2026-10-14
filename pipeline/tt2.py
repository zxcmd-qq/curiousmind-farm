"""GitHub: пост из ТГК (фото/альбом) → карусель в TikTok @obezyanagrustnaya (в черновики).
Слайд 1 — шаблон-обложка с началом текста с картинки («В ПСКОВЕ…» + стрелка), дальше все фото поста.
Вход — env PAYLOAD: {"files": [file_id...], "caption": "...", "post": "chan_msgid", "chan": "название"}"""
import base64, io, json, os, re, subprocess, sys, time
import requests
from PIL import Image, ImageDraw, ImageFont
from common import E, log, tg, gemini

P = json.loads(E["PAYLOAD"])
REPO = E["GITHUB_REPOSITORY"]
PAGES_REPO = E.get("TT2_PAGES_REPO", "zxcmd-qq/zxcmd-qq.github.io")
PAGES_URL = E.get("TT2_PAGES_URL", "https://zxcmd-qq.github.io")
POST = re.sub(r"[^\w-]", "_", P.get("post") or str(int(time.time())))
FONT = "resource/fonts/Montserrat-Medium.ttf"
os.makedirs("tt2", exist_ok=True)


def tg_file(fid):
    i = requests.get(f"https://api.telegram.org/bot{E['TG_BOT_TOKEN']}/getFile", params={"file_id": fid}, timeout=30).json()
    if not i.get("ok"):
        raise RuntimeError("getFile: " + str(i)[:200])
    return requests.get(f"https://api.telegram.org/file/bot{E['TG_BOT_TOKEN']}/{i['result']['file_path']}", timeout=120).content


# ---------- 1. фото поста
photos = []
for fid in P["files"][:34]:
    im = Image.open(io.BytesIO(tg_file(fid))).convert("RGB")
    photos.append(im)
log("фото:", len(photos))

# ---------- 2. начало текста с первой картинки (Gemini читает картинку)
def ocr(im):
    b = io.BytesIO(); im.save(b, "JPEG", quality=92)
    img = base64.b64encode(b.getvalue()).decode()
    ask = ("На картинке-меме есть текст (заголовок или подпись). Перепиши ВЕСЬ этот текст дословно, как написано, "
           "без ников, водяных знаков и названий каналов. Ответь ТОЛЬКО JSON: {\"text\": \"...\"}. Если текста нет — {\"text\": \"\"}.")
    for model in ("gemini-flash-latest", "gemini-flash-lite-latest", "gemini-flash-latest"):
        try:
            r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                              headers={"x-goog-api-key": E["GEMINI_KEY"]}, timeout=90, json={
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
                "contents": [{"parts": [{"inlineData": {"mimeType": "image/jpeg", "data": img}}, {"text": ask}]}]}).json()
            t = r["candidates"][0]["content"]["parts"][0]["text"]
            txt = json.loads(t[t.find("{"):t.rfind("}") + 1]).get("text", "").strip()
            log(f"OCR ({model}):", txt[:120])
            return txt
        except Exception as e:
            log(f"OCR ({model}) ошибка:", str(e)[:150], str(locals().get("r", ""))[:300])
            time.sleep(8)
    return ""


def start_of(text, n_words=3, max_chars=22):
    words = re.sub(r"\s+", " ", text).strip().split(" ")
    out = ""
    for w in words[:n_words]:
        if out and len(out) + 1 + len(w) > max_chars:
            break
        out = (out + " " + w).strip()
    return out


full = ocr(photos[0])
hook = start_of(full) or start_of(P.get("caption") or "")
hook = (hook.rstrip(" .…!?,:;-") + "...") if hook else "СМОТРИ ДО КОНЦА..."
log("обложка:", hook)


# ---------- 3. обложка: шаблон + текст по центру + стрелка вправо
def cover():
    try:
        subprocess.run(["gh", "release", "download", "assets", "-p", "tt2-cover.jpg", "-D", "tt2", "--clobber", "-R", REPO], check=True, capture_output=True)
        base = Image.open("tt2/tt2-cover.jpg").convert("RGB")
    except Exception:
        base = Image.new("RGB", (1080, 1350), "#111")
    W, H = base.size
    d = ImageDraw.Draw(base)
    size = int(W * 0.085)
    while size > 30:
        f = ImageFont.truetype(FONT, size)
        words, lines, cur = hook.split(), [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if d.textlength(t, font=f) <= W * 0.86 or not cur:
                cur = t
            else:
                lines.append(cur); cur = w
        lines.append(cur)
        if len(lines) <= 3 and max(d.textlength(l, font=f) for l in lines) <= W * 0.88:
            break
        size -= 6
    lh = int(size * 1.25)
    arrow_h = int(size * 0.9)
    total = lh * len(lines) + int(size * 0.35) + arrow_h
    y = (H - total) // 2
    sw = max(2, size // 18)
    for l in lines:
        x = (W - d.textlength(l, font=f)) / 2
        d.text((x, y), l, font=f, fill="#FFFFFF", stroke_width=sw, stroke_fill="#000000")
        y += lh
    # стрелка ➜ (рисуем сами, чтобы не зависеть от шрифта)
    y += int(size * 0.35)
    aw, cx = int(size * 1.6), W // 2
    shaft = [(cx - aw // 2, y + arrow_h * 0.32), (cx + aw * 0.12, y + arrow_h * 0.32), (cx + aw * 0.12, y),
             (cx + aw // 2, y + arrow_h / 2), (cx + aw * 0.12, y + arrow_h), (cx + aw * 0.12, y + arrow_h * 0.68),
             (cx - aw // 2, y + arrow_h * 0.68)]
    d.polygon(shaft, fill="#FFFFFF", outline="#000000", width=sw)
    return base


slides = [cover()] + photos

# ---------- 4. кладём на GitHub Pages (TikTok берёт фото только с проверенного домена)
urls = []
for i, im in enumerate(slides):
    b = io.BytesIO()
    im.save(b, "JPEG", quality=90)
    path = f"tt/{POST}/{i}.jpg"
    r = requests.put(f"https://api.github.com/repos/{PAGES_REPO}/contents/{path}", timeout=60,
                     headers={"Authorization": f"Bearer {E['GH_PAT']}", "Accept": "application/vnd.github+json"},
                     json={"message": f"tt2 {POST}", "content": base64.b64encode(b.getvalue()).decode()})
    if r.status_code not in (200, 201):
        raise RuntimeError("GitHub Pages upload: " + r.text[:200])
    urls.append(f"{PAGES_URL}/{path}")
log("ждём публикации Pages…")
for _ in range(40):
    time.sleep(10)
    if all(requests.head(u, timeout=20).status_code == 200 for u in (urls[0], urls[-1])):
        break

# ---------- 5. описание
cap = (P.get("caption") or "").strip()
try:
    d = gemini("Ты SMM-специалист TikTok. Пост-прикол (карусель картинок). Текст поста из Telegram: «" + (cap or hook) + "». "
               "Напиши короткое описание на русском (до 150 символов, с юмором, без ссылок и упоминаний Telegram) и 4 хештега по теме "
               "(без #fyp, #рек, без слов про криминал, насилие, 18+, политику, шок). Ответь ТОЛЬКО JSON: {\"text\":\"...\",\"tags\":[\"...\"]}", temperature=0.8)
    desc = d.get("text", "").strip() + "\n\n" + " ".join("#" + t.lstrip("#").replace(" ", "") for t in d.get("tags", [])[:4])
except Exception:
    desc = cap[:150] or hook
title = (cap.split("\n")[0] if cap else hook)[:85]

# ---------- 6. TikTok: карусель в черновики
t = requests.post("https://open.tiktokapis.com/v2/oauth/token/", timeout=30, data={
    "client_key": E["TT_CLIENT_KEY"], "client_secret": E["TT_CLIENT_SECRET"],
    "grant_type": "refresh_token", "refresh_token": E["TT2_REFRESH_TOKEN"]}).json()
if "access_token" not in t:
    tg("sendMessage", chat=E["TG_CHAT_ID"], text="❌ TikTok-2: токен не обновился: " + str(t)[:200])
    sys.exit(1)
if t.get("refresh_token") and t["refresh_token"] != E["TT2_REFRESH_TOKEN"]:
    subprocess.run(["gh", "secret", "set", "TT2_REFRESH_TOKEN", "-R", REPO], input=t["refresh_token"], text=True,
                   env={**os.environ, "GH_TOKEN": E["GH_PAT"]}, capture_output=True)
init = requests.post("https://open.tiktokapis.com/v2/post/publish/content/init/", timeout=60,
                     headers={"Authorization": "Bearer " + t["access_token"], "Content-Type": "application/json; charset=UTF-8"},
                     json={"post_info": {"title": title, "description": desc[:4000]},
                           "source_info": {"source": "PULL_FROM_URL", "photo_cover_index": 0, "photo_images": urls},
                           "post_mode": "MEDIA_UPLOAD", "media_type": "PHOTO"}).json()
ok = (init.get("error") or {}).get("code") == "ok" and (init.get("data") or {}).get("publish_id")
esc = desc.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
if ok:
    tg("sendMessage", chat=E["TG_CHAT_ID"], parse_mode="HTML",
       text=f"📸 Карусель ({len(slides)} слайдов, обложка «{hook}») ушла в черновики TikTok @obezyanagrustnaya.\n\nОписание (тапни, чтобы скопировать):\n<code>{esc}</code>")
else:
    tg("sendMessage", chat=E["TG_CHAT_ID"], text="❌ TikTok-2 карусель: " + json.dumps(init, ensure_ascii=False)[:400])
    sys.exit(1)
