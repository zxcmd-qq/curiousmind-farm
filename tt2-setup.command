#!/bin/bash
# Подключение второго TikTok (@obezyanagrustnaya) для каруселей из ТГК.
# Шаг А: вход в TikTok-2 → секрет TT2_REFRESH_TOKEN в GitHub.
# Шаг Б: файл подтверждения домена TikTok → https://zxcmd-qq.github.io/tt/
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
cd "$(dirname "$0")"
PY="$HOME/MoneyPrinterTurbo/.venv/bin/python"
R=$(gh repo view --json nameWithOwner -q .nameWithOwner)
GHU=$(gh api user -q .login)

echo "== А. Вход во ВТОРОЙ TikTok"
echo "ВАЖНО: в браузере должен быть открыт аккаунт @obezyanagrustnaya (выйди из основного или открой окно инкогнито и скопируй ссылку туда)."
"$PY" - "$R" <<'EOF'
import json, os, subprocess, sys, urllib.parse, webbrowser
import requests
t = json.load(open(os.path.expanduser("~/Documents/n8n-autopost/tiktok.json")))
ck, cs = t["client_key"], t["client_secret"]
gh = subprocess.check_output(["gh", "api", "user", "-q", ".login"], text=True).strip()
redirect = f"https://{gh}.github.io/callback.html"
url = "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode({
    "client_key": ck, "scope": "user.info.basic,video.upload,video.publish", "response_type": "code",
    "redirect_uri": redirect, "state": "tt2"})
print("\nСсылка для входа (если браузер открыл не тот аккаунт — вставь её в инкогнито):\n" + url + "\n")
webbrowser.open(url)
code = urllib.parse.unquote(input("Вставь код со страницы и нажми Enter:\n> ").strip())
d = requests.post("https://open.tiktokapis.com/v2/oauth/token/", timeout=30, data={
    "client_key": ck, "client_secret": cs, "code": code, "grant_type": "authorization_code", "redirect_uri": redirect}).json()
if "refresh_token" not in d:
    print("❌ Не получилось:", d.get("error_description") or d); sys.exit(1)
subprocess.run(["gh", "secret", "set", "TT2_REFRESH_TOKEN", "-R", sys.argv[1]], input=d["refresh_token"], text=True, check=True)
print("✅ TikTok-2 подключён. Доступ:", d.get("scope"))
EOF

echo
echo "== Б. Подтверждение домена для фото"
echo "В TikTok for Developers → твоё приложение → URL properties → Add → URL prefix:"
echo "   https://$GHU.github.io/tt/"
echo "Скачай файл подтверждения (tiktok*.txt) в Загрузки и нажми Enter."
read -r
F=$(ls -t "$HOME/Downloads"/tiktok*.txt 2>/dev/null | head -1)
if [ -z "$F" ]; then echo "❌ Не нашёл tiktok*.txt в Загрузках"; exit 1; fi
N=$(basename "$F")
gh api -X PUT "repos/$GHU/$GHU.github.io/contents/tt/$N" -f message="tiktok verify" -f content="$(base64 -i "$F" | tr -d '\n')" > /dev/null \
  && echo "✅ Файл выложен: https://$GHU.github.io/tt/$N — через минуту жми Verify в TikTok."
echo
read -n 1 -s -r -p "Нажми любую клавишу, чтобы закрыть..."
