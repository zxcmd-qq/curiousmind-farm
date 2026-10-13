"""Общие штуки для скриптов на GitHub: Telegram, Gemini, YouTube-токен."""
import json, os, time
import requests

E = os.environ


def log(*a):
    print("▶", *a, flush=True)


def tg(method, chat=None, token=None, files=None, **data):
    token = token or E["TG_BOT_TOKEN"]
    if chat is not None:
        data["chat_id"] = chat
    if files:
        data = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v) for k, v in data.items()}
        r = requests.post(f"https://api.telegram.org/bot{token}/{method}", data=data, files=files, timeout=600)
    else:
        r = requests.post(f"https://api.telegram.org/bot{token}/{method}", json=data, timeout=60)
    j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"ok": False, "raw": r.text[:300]}
    if not j.get("ok"):
        log("telegram", method, str(j)[:300])
    return j


def gemini(prompt, model="gemini-flash-lite-latest", temperature=1.0, tries=4):
    for i in range(1, tries + 1):
        try:
            r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                              headers={"x-goog-api-key": E["GEMINI_KEY"]}, timeout=120,
                              json={"generationConfig": {"responseMimeType": "application/json", "temperature": temperature},
                                    "contents": [{"parts": [{"text": prompt}]}]}).json()
        except Exception as e:
            r = {"error": {"message": str(e)}}
        txt = (((r.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [{}])[0].get("text", "")
        if txt:
            s, e2 = txt.find("{"), txt.rfind("}")
            return json.loads(txt[s:e2 + 1])
        log(f"Gemini попытка {i}:", str(r)[:300])
        time.sleep(20 * i)
    raise RuntimeError("Gemini не ответил")


def yt_access_token():
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": E["YT_CLIENT_ID"], "client_secret": E["YT_CLIENT_SECRET"],
        "refresh_token": E["YT_REFRESH_TOKEN"], "grant_type": "refresh_token"}, timeout=30).json()
    if "access_token" not in r:
        raise RuntimeError("YouTube токен: " + str(r)[:300])
    return r["access_token"]
