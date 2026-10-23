"""Подгоняет config.toml с Мака под сервер GitHub: пути к фонам и т.п."""
import os, re, sys

path, bg = sys.argv[1], sys.argv[2]
s = open(path, encoding="utf-8").read()
s = re.sub(r'(?m)^gameplay_dirs\s*=.*\n', '', s)
s = re.sub(r'(?m)^autopost_inbox\s*=.*\n', '', s)
s = re.sub(r'(?m)^listen_host\s*=.*$', 'listen_host = "127.0.0.1"', s)
s = s.replace("[app]\n", f'[app]\ngameplay_dirs = ["{bg}/minecraft", "{bg}/satisfy"]\n', 1)
# ключ ElevenLabs из бота (/elkey) важнее ключа из старого конфига
k = os.environ.get("ELEVENLABS_API_KEY", "").strip()
if k:
    m = re.search(r'(?ms)^\[elevenlabs\]\n(.*?)(?=^\[|\Z)', s)
    if m:
        body = re.sub(r'(?m)^api_key\s*=.*\n?', '', m.group(1))
        s = s[:m.start(1)] + f'api_key = "{k}"\n' + body + s[m.end(1):]
    else:
        s += f'\n[elevenlabs]\napi_key = "{k}"\n'
open(path, "w", encoding="utf-8").write(s)
print("config ok")
