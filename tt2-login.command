#!/bin/bash
# Вход во ВТОРОЙ TikTok (@obezyanagrustnaya) → секрет TT2_REFRESH_TOKEN в GitHub.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
cd "$(dirname "$0")"
PY="$HOME/MoneyPrinterTurbo/.venv/bin/python"
R=$(gh repo view --json nameWithOwner -q .nameWithOwner)
TMP=$(mktemp /tmp/tt2login.XXXX.py)
cat > "$TMP" <<'EOF'
import json, os, subprocess, sys, urllib.parse, webbrowser
import requests
t = json.load(open(os.path.expanduser("~/Documents/n8n-autopost/tiktok.json")))
ck, cs = t["client_key"], t["client_secret"]
gh = subprocess.check_output(["gh", "api", "user", "-q", ".login"], text=True).strip()
redirect = f"https://{gh}.github.io/callback.html"
url = "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode({
    "client_key": ck, "scope": "user.info.basic,video.upload,video.publish", "response_type": "code",
    "redirect_uri": redirect, "state": "tt2"})
print("ВАЖНО: в браузере должен быть @obezyanagrustnaya. Если открылся основной — вставь ссылку в инкогнито:\n\n" + url + "\n")
webbrowser.open(url)
code = urllib.parse.unquote(input("Вставь код со страницы и нажми Enter:\n> ").strip())
d = requests.post("https://open.tiktokapis.com/v2/oauth/token/", timeout=30, data={
    "client_key": ck, "client_secret": cs, "code": code, "grant_type": "authorization_code", "redirect_uri": redirect}).json()
if "refresh_token" not in d:
    print("❌ Не получилось:", d.get("error_description") or d); sys.exit(1)
subprocess.run(["gh", "secret", "set", "TT2_REFRESH_TOKEN", "-R", sys.argv[1]], input=d["refresh_token"], text=True, check=True)
print("✅ TikTok-2 подключён. Доступ:", d.get("scope"))
EOF
"$PY" "$TMP" "$R"
rm -f "$TMP"
echo; read -n 1 -s -r -p "Нажми любую клавишу, чтобы закрыть..."
