"""GitHub: раз в неделю статистика YouTube + Instagram → выводы Gemini → state/insights.json + отчёт в ТГ."""
import json, os, re, time
import requests
from common import E, log, tg, gemini, yt_access_token

DAYS = int(E.get("DAYS", 45))
since = time.time() - DAYS * 86400
day = lambda s: str(s or "")[:10]
ts = lambda s: time.mktime(time.strptime(str(s)[:19], "%Y-%m-%dT%H:%M:%S"))
CATS = re.findall(r"'([^']+)'", re.search(r"const CATS = \[([\s\S]*?)\];", open("pipeline/nodes/Pick_Format.js", encoding="utf-8").read()).group(1))

# --- YouTube
yt = []
try:
    H = {"Authorization": "Bearer " + yt_access_token()}
    G = "https://www.googleapis.com/youtube/v3/"
    up = requests.get(G + "channels?part=contentDetails&mine=true", headers=H, timeout=30).json()["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    ids = [i["contentDetails"]["videoId"] for i in requests.get(G + f"playlistItems?part=contentDetails&maxResults=50&playlistId={up}", headers=H, timeout=30).json().get("items", [])]
    for v in requests.get(G + "videos?part=snippet,statistics&id=" + ",".join(ids), headers=H, timeout=30).json().get("items", []):
        if ts(v["snippet"]["publishedAt"]) < since:
            continue
        s = v.get("statistics", {})
        yt.append({"d": day(v["snippet"]["publishedAt"]), "t": re.sub(r"\s*#Shorts", "", v["snippet"]["title"], flags=re.I)[:90],
                   "views": int(s.get("viewCount", 0)), "likes": int(s.get("likeCount", 0)), "comments": int(s.get("commentCount", 0))})
except Exception as e:
    log("YouTube:", e)

# --- Instagram
ig = []
try:
    IG = "https://graph.instagram.com/v23.0/"
    media = requests.get(IG + f"{E['IG_USER_ID']}/media", timeout=30, params={"fields": "id,caption,timestamp,like_count,comments_count",
                         "limit": 50, "access_token": E["IG_TOKEN"]}).json().get("data", [])
    for m in media[:40]:
        if ts(m["timestamp"]) < since:
            continue
        r = {"d": day(m["timestamp"]), "t": (m.get("caption") or "").split("\n\n#")[0][:160], "likes": m.get("like_count", 0), "comments": m.get("comments_count", 0)}
        try:
            for x in requests.get(IG + f"{m['id']}/insights", timeout=30, params={"metric": "views,reach,saved,shares", "access_token": E["IG_TOKEN"]}).json().get("data", []):
                r[x["name"]] = (x.get("values") or [{}])[0].get("value") or (x.get("total_value") or {}).get("value") or 0
        except Exception:
            pass
        ig.append(r)
except Exception as e:
    log("Instagram:", e)

fmt = lambda r: " | ".join(f"{k}={v}" for k, v in r.items())
yt.sort(key=lambda r: -r["views"])
ig.sort(key=lambda r: -(r.get("views") or r.get("likes") or 0))
log(f"YT: {len(yt)}, IG: {len(ig)}")
prompt = ("Ты аналитик короткого видео-канала Curious Mind (TikTok/YouTube Shorts/Instagram Reels, аудитория — Россия/СНГ). "
          "Форматы: «факт» (интересный факт), «квиз» (вопрос с вариантами А/Б/В), «история» (пересказ истории с Пикабу; бывают «Часть 1/Часть 2»). "
          f"Формат и тему определи по названию.\n\nСтатистика за последние {DAYS} дней.\n\nYOUTUBE SHORTS (по убыванию просмотров):\n"
          + ("\n".join(map(fmt, yt)) or "нет данных") + "\n\nINSTAGRAM REELS:\n" + ("\n".join(map(fmt, ig)) or "нет данных")
          + "\n\nКатегории тем, из которых сценарист выбирает факты и квизы:\n" + "\n".join(CATS)
          + "\n\nЗадача: найди закономерности — какие темы, форматы, крючки и подачи набирают больше просмотров/лайков/комментов, а какие проваливаются. "
            "Делай выводы только из цифр, не выдумывай. Если данных мало — так и скажи и дай осторожные выводы.\n"
            'Ответь ТОЛЬКО JSON: {"report": "отчёт для автора по-русски, 6-10 коротких строк с цифрами: что зашло, что нет, лучший формат, что делать дальше", '
            '"tips": ["3-6 коротких конкретных правил для сценариста: какие темы и подачу брать"], "avoid": ["2-4 что не заходит"], '
            '"format_rank": ["facts|quiz|reddit от лучшего к худшему"], "cat_weights": {"<каждая категория из списка дословно>": число от 0.3 (не заходит) до 3 (зашло), 1 если данных нет}}')
r = gemini(prompt, model="gemini-flash-latest", temperature=0.4)
ins = {"updated": time.strftime("%Y-%m-%d"), "tips": (r.get("tips") or [])[:6], "avoid": (r.get("avoid") or [])[:4],
       "format_rank": r.get("format_rank") or [], "cat_weights": r.get("cat_weights") or {}}
json.dump(ins, open("state/insights.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
hot = sorted(ins["cat_weights"].items(), key=lambda kv: -float(kv[1] or 0))[:3]
msg = (f"📊 Отчёт Curious Mind ({len(yt)} YT / {len(ig)} IG роликов)\n\n{r.get('report', '')}"
       + ("\n\n🏆 Топ YouTube:\n" + "\n".join(f"{i + 1}. {v['t']} — {v['views']} 👁" for i, v in enumerate(yt[:3])) if yt else "")
       + "\n\n🧠 Учту в новых сценариях:\n• " + "\n• ".join(ins["tips"])
       + ("\n\n🚫 Буду избегать:\n• " + "\n• ".join(ins["avoid"]) if ins["avoid"] else "")
       + ("\n\n🔥 Чаще беру темы: " + ", ".join(f"{k} ×{v}" for k, v in hot) if hot else ""))
tg("sendMessage", chat=E["TG_CHAT_ID"], text=msg[:4000], disable_web_page_preview=True)
log("insights сохранены")

# --- продлеваем IG-токен (живёт 60 дней) и обновляем секрет
try:
    import subprocess
    t = requests.get("https://graph.instagram.com/refresh_access_token", timeout=30,
                     params={"grant_type": "ig_refresh_token", "access_token": E["IG_TOKEN"]}).json()
    if t.get("access_token") and E.get("GH_PAT"):
        subprocess.run(["gh", "secret", "set", "IG_TOKEN", "-R", E["GITHUB_REPOSITORY"]], input=t["access_token"], text=True,
                       env={**os.environ, "GH_TOKEN": E["GH_PAT"]}, check=True, capture_output=True)
        log("IG-токен продлён")
    else:
        log("IG-токен:", str(t)[:200])
except Exception as e:
    log("IG-токен:", e)
