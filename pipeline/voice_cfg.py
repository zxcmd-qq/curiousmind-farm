"""GitHub: берёт голос и ключ ElevenLabs из бота (cm-bot, команды /voice и /elkey).
Если у ElevenLabs кончились символы или ключа нет — сам переключает на Gemini и пишет в ТГ."""
import os, requests

E = os.environ
URL = (E.get("CM_BOT_URL") or "https://cm-bot.osttima.workers.dev").rstrip("/") + "/cfg"
FALLBACK = E.get("VOICE") or "gemini:Fenrir-Excitable"
NEED = 1500  # символов на один ролик с запасом


def tg(text):
    try:
        requests.post(f"https://api.telegram.org/bot{E['TG_BOT_TOKEN']}/sendMessage", timeout=20,
                      json={"chat_id": E["TG_CHAT_ID"], "text": text})
    except Exception:
        pass


cfg = {}
try:
    cfg = requests.get(URL, headers={"Authorization": "Bearer " + E.get("GH_PAT", "")}, timeout=20).json()
except Exception as e:
    print("бот не ответил:", str(e)[:150])
voice, key = (cfg.get("voice") or "").strip(), (cfg.get("elkey") or "").strip()
if key:
    print(f"::add-mask::{key}")
if voice.startswith("elevenlabs:"):
    left = None
    if key:
        try:
            r = requests.get("https://api.elevenlabs.io/v1/user/subscription", headers={"xi-api-key": key}, timeout=20)
            if r.ok:
                j = r.json(); left = (j.get("character_limit") or 0) - (j.get("character_count") or 0)
        except Exception:
            pass
    if not key or (left is not None and left < NEED):
        why = "нет ключа" if not key else f"осталось {left} символов"
        print(f"ElevenLabs: {why} → {FALLBACK}")
        tg(f"🎙 ElevenLabs: {why}. Этот ролик озвучу голосом {FALLBACK}.\nНовый ключ — /elkey ключ")
        voice = FALLBACK
    else:
        print("ElevenLabs ок, осталось:", left if left is not None else "неизвестно")
voice = voice or FALLBACK
print("голос:", voice)
with open(E["GITHUB_ENV"], "a") as f:
    f.write(f"CM_VOICE={voice}\n")
    if key:
        f.write(f"ELEVENLABS_API_KEY={key}\n")
