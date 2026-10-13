"""Подгоняет config.toml с Мака под сервер GitHub: пути к фонам и т.п."""
import re, sys

path, bg = sys.argv[1], sys.argv[2]
s = open(path, encoding="utf-8").read()
s = re.sub(r'(?m)^gameplay_dirs\s*=.*\n', '', s)
s = re.sub(r'(?m)^autopost_inbox\s*=.*\n', '', s)
s = re.sub(r'(?m)^listen_host\s*=.*$', 'listen_host = "127.0.0.1"', s)
s = s.replace("[app]\n", f'[app]\ngameplay_dirs = ["{bg}/minecraft", "{bg}/satisfy"]\n', 1)
open(path, "w", encoding="utf-8").write(s)
print("config ok")
