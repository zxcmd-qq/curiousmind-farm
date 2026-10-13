"""GitHub: публикация одобренного ролика на все площадки.
publish.py <id>  — берёт <id>.mp4 и <id>.json из релиза videos."""
import json, os, re, subprocess, sys, time
import requests
from common import E, log, tg, gemini, yt_access_token

ID = sys.argv[1]
REPO = E["GITHUB_REPOSITORY"]
os.makedirs("pub", exist_ok=True)
subprocess.run(["gh", "release", "download", "videos", "-p", f"{ID}.*", "-D", "pub", "--clobber", "-R", REPO], check=True)
meta = json.load(open(f"pub/{ID}.json", encoding="utf-8"))
VIDEO = f"pub/{ID}.mp4"
SIZE = os.path.getsize(VIDEO)
topic = meta.get("topic") or "Интересное"
log("публикую:", topic, f"{SIZE / 1048576:.1f} МБ")
res = {}

# ---------- описание (как в старом автопосте)
# Правила площадок (TikTok «For You», Meta «снижение охвата», YouTube): за эти слова режут показы или не рекомендуют.
SAFE = ("ПРАВИЛА БЕЗОПАСНОСТИ (TikTok, Instagram, YouTube режут охват за это): в заголовке, описании и хештегах НЕ используй слова и теги про "
        "преступления и криминал (кража, вор, украл, ограбление, мошенник, развод, тюрьма, полиция, убийство, маньяк), насилие и кровь "
        "(драка, избил, кровь, жестокость, смерть, труп, авария, катастрофа, жертвы), оружие и взрывы, наркотики, алкоголь, курение, азартные игры, "
        "секс и 18+, суицид, болезни и травмы, политику, войну, религию, а также шок-кликбейт (жесть, шок, ужас, кошмар, треш, страшно, "
        "вы не поверите, 99% не знают). Если тема сама про такое — опиши её мягко и нейтрально (например «история о хитром плане», «загадка истории»). "
        "Без призывов «лайкни/подпишись ради...», без вопросов «напиши в комментах, если...» ради накрутки, без #fyp #рек #рекомендации #viral #xyzbca. "
        "Хештеги — только нейтральные и по теме: про познавательное, факты, историю, науку, юмор, жизнь.")
BAD_TAG = re.compile(r"краж|^вор(ы|ов|ишк\w*)?$|ворую|воруют|украл|ограб|мошен|развод|тюрьм|полиц|убий|маньяк|драк|изби|кров|жест|смерт|труп|авари|катастроф|жертв|оруж|взрыв|"
                     r"нарко|алко|пьян|курен|казино|ставк|секс|18|суицид|болезн|травм|политик|войн|религ|шок|ужас|кошмар|треш|страш|fyp|^рек$|рекомендац|viral|xyz", re.I)
try:
    d = gemini(f'Ты SMM-специалист. Тема короткого вертикального видео: "{topic}". Напиши на русском языке: цепляющий, но спокойный заголовок (до 80 символов), '
               'описание 1-3 предложения (вызывает любопытство, без кликбейта), и 8-12 релевантных хештегов, ОТСОРТИРОВАННЫХ по важности: первые 5 — лучшие для TikTok '
               '(2 широких популярных + 3 точных по теме видео). ' + SAFE + ' Ответь ТОЛЬКО JSON: {"title":"...","description":"...","hashtags":["..."]}', temperature=0.7)
except Exception as e:
    log("описание:", e)
    d = {"title": topic, "description": topic, "hashtags": ["интересныефакты", "факты", "познавательно", "знаешьли", "curiousmind"]}
tags = [re.sub(r"\s+", "", t.lstrip("#")) for t in d.get("hashtags", []) if t]
dropped = [t for t in tags if BAD_TAG.search(t)]
tags = [t for t in tags if not BAD_TAG.search(t)] or ["интересныефакты", "факты", "познавательно"]
if dropped:
    log("выкинул опасные хештеги:", dropped)
title = (d.get("title") or topic)[:90]
desc = d.get("description") or topic
caption = (desc + "\n\n" + " ".join("#" + t for t in tags))[:2150]

# ---------- YouTube Shorts
try:
    tok = yt_access_token()
    body = {"snippet": {"title": (title + " #Shorts")[:100], "description": caption[:4900], "tags": tags[:15], "categoryId": "22"},
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}
    r = requests.post("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                      headers={"Authorization": "Bearer " + tok, "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(SIZE)},
                      json=body, timeout=60)
    loc = r.headers.get("Location") or (_ for _ in ()).throw(RuntimeError(r.text[:300]))
    with open(VIDEO, "rb") as f:
        v = requests.put(loc, data=f, headers={"Authorization": "Bearer " + tok, "Content-Type": "video/mp4"}, timeout=900).json()
    res["YouTube"] = "✅ https://youtube.com/shorts/" + v["id"]
except Exception as e:
    res["YouTube"] = "❌ " + str(e)[:200]

# ---------- Telegram-канал (+ викторина для квиза)
try:
    with open(VIDEO, "rb") as f:
        j = tg("sendVideo", chat=E["TG_CHANNEL"], token=E["TG_CHANNEL_BOT_TOKEN"], files={"video": ("video.mp4", f, "video/mp4")},
               caption=caption[:1000], width=1080, height=1920, supports_streaming="true")
    res["Telegram"] = "✅" if j.get("ok") else "❌ " + str(j)[:200]
    q = meta.get("quiz")
    if j.get("ok") and q and len(q.get("options") or []) >= 2:
        opts = [str(o)[:100] for o in q["options"][:3]]
        p = {"question": ("❓ " + str(q.get("topic") or topic))[:300], "options": [{"text": o} for o in opts], "type": "quiz",
             "is_anonymous": True, "correct_option_id": max(0, min(len(opts) - 1, int(q.get("answer", 0))))}
        if q.get("explain"):
            p["explanation"] = str(q["explain"])[:200]
        pj = tg("sendPoll", chat=E["TG_CHANNEL"], token=E["TG_CHANNEL_BOT_TOKEN"], **p)
        res["Викторина"] = "✅" if pj.get("ok") else "❌ " + str(pj)[:150]
except Exception as e:
    res["Telegram"] = "❌ " + str(e)[:200]

# ---------- TikTok (в черновики/инбокс, как раньше)
try:
    t = requests.post("https://open.tiktokapis.com/v2/oauth/token/", timeout=30, data={
        "client_key": E["TT_CLIENT_KEY"], "client_secret": E["TT_CLIENT_SECRET"],
        "grant_type": "refresh_token", "refresh_token": E["TT_REFRESH_TOKEN"]}).json()
    if "access_token" not in t:
        raise RuntimeError("токен: " + str(t)[:200])
    if t.get("refresh_token") and t["refresh_token"] != E["TT_REFRESH_TOKEN"] and E.get("GH_PAT"):
        subprocess.run(["gh", "secret", "set", "TT_REFRESH_TOKEN", "-b", t["refresh_token"], "-R", REPO],
                       env={**os.environ, "GH_TOKEN": E["GH_PAT"]}, check=False)
        log("TikTok: refresh-токен обновлён")
    init = requests.post("https://open.tiktokapis.com/v2/post/publish/inbox/video/init/", timeout=60,
                         headers={"Authorization": "Bearer " + t["access_token"], "Content-Type": "application/json; charset=UTF-8"},
                         json={"source_info": {"source": "FILE_UPLOAD", "video_size": SIZE, "chunk_size": SIZE, "total_chunk_count": 1}}).json()
    url = (init.get("data") or {}).get("upload_url") or (_ for _ in ()).throw(RuntimeError(str(init)[:200]))
    with open(VIDEO, "rb") as f:
        u = requests.put(url, data=f, timeout=900, headers={"Content-Type": "video/mp4", "Content-Range": f"bytes 0-{SIZE - 1}/{SIZE}"})
    res["TikTok"] = "✅ в черновиках" if u.status_code < 300 else f"❌ upload {u.status_code}"
    tt_text = desc + "\n\n" + " ".join("#" + x for x in tags[:5])
    esc = tt_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    tg("sendMessage", chat=E["TG_CHAT_ID"], text="🎵 Описание для TikTok (тапни, чтобы скопировать):\n\n<code>" + esc + "</code>", parse_mode="HTML")
except Exception as e:
    res["TikTok"] = "❌ " + str(e)[:200]


# ---------- Instagram Reels (нужна прямая ссылка на файл)
def host(path):
    tries = [
        lambda: requests.post("https://litterbox.catbox.moe/resources/internals/api.php", timeout=240,
                              data={"reqtype": "fileupload", "time": "24h"}, files={"fileToUpload": ("video.mp4", open(path, "rb"))}).text.strip(),
        lambda: requests.post("https://uguu.se/upload", timeout=240, files={"files[]": ("video.mp4", open(path, "rb"))}).json()["files"][0]["url"],
        lambda: requests.post("https://tmpfiles.org/api/v1/upload", timeout=240, files={"file": ("video.mp4", open(path, "rb"))}).json()["data"]["url"]
        .replace("http://", "https://").replace("tmpfiles.org/", "tmpfiles.org/dl/", 1),
    ]
    for fn in tries:
        for _ in range(2):
            try:
                u = fn()
                if u.startswith("https://"):
                    return u
            except Exception as e:
                log("хостинг:", str(e)[:120])
            time.sleep(3)
    raise RuntimeError("все хостинги отказали")


try:
    G = "https://graph.instagram.com/v23.0/"
    vurl = host(VIDEO)
    c = requests.post(G + f"{E['IG_USER_ID']}/media", timeout=60, params={
        "media_type": "REELS", "video_url": vurl, "caption": caption, "thumb_offset": 1000, "access_token": E["IG_TOKEN"]}).json()
    cid = c.get("id") or (_ for _ in ()).throw(RuntimeError(str(c)[:200]))
    for _ in range(40):
        time.sleep(15)
        st = requests.get(G + cid, timeout=30, params={"fields": "status_code,status", "access_token": E["IG_TOKEN"]}).json()
        if st.get("status_code") in ("FINISHED", "ERROR", "EXPIRED"):
            break
    if st.get("status_code") != "FINISHED":
        raise RuntimeError("обработка: " + str(st)[:200])
    p = requests.post(G + f"{E['IG_USER_ID']}/media_publish", timeout=60, params={"creation_id": cid, "access_token": E["IG_TOKEN"]}).json()
    res["Instagram"] = "✅" if p.get("id") else "❌ " + str(p)[:200]
except Exception as e:
    res["Instagram"] = "❌ " + str(e)[:200]

# ---------- отчёт
report = f"📤 {meta.get('label', '')}: {topic}\n\n" + "\n".join(f"{k}: {v}" for k, v in res.items())
tg("sendMessage", chat=E["TG_CHAT_ID"], text=report[:4000], disable_web_page_preview=True)
log(report)
if all(str(v).startswith("❌") for v in res.values()):
    sys.exit(1)
