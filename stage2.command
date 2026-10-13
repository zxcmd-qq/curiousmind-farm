#!/bin/bash
# Этап 2: подборка недели, статистика и постинг на GitHub. Токены берутся с этого Мака и уходят прямо в GitHub Secrets.
set -e
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
cd "$(dirname "$0")"
A="$HOME/Documents/n8n-autopost"
PY="$HOME/MoneyPrinterTurbo/.venv/bin/python"
R=$(gh repo view --json nameWithOwner -q .nameWithOwner)
echo "репо: $R"

echo "== 1/4 Код"
mkdir -p .github/workflows && cp pipeline/workflows/*.yml .github/workflows/
git add -A
git -c user.name="$(gh api user -q .login)" -c user.email="bot@users.noreply.github.com" commit -q -m "stage 2: weekly, stats, publish" || true
git pull --rebase -q && git push -q

echo "== 2/4 Секреты из n8n (расшифровываются тут, на Маке)"
"$PY" - <<'EOF' > /tmp/cm_s2.json
import base64, hashlib, json, os, re, sqlite3
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
H = os.path.expanduser("~")
key = json.load(open(f"{H}/.n8n/config"))["encryptionKey"]
def dec(data):
    raw = base64.b64decode(data); salt, ct = raw[8:16], raw[16:]; d = b""; prev = b""
    while len(d) < 48:
        prev = hashlib.md5(prev + key.encode() + salt).digest(); d += prev
    p = Cipher(algorithms.AES(d[:32]), modes.CBC(d[32:48])).decryptor(); out = p.update(ct) + p.finalize()
    return json.loads(out[:-out[-1]])
c = sqlite3.connect(f"{H}/.n8n/database.sqlite")
cred = {i: dec(d) for i, d in c.execute("select id, data from credentials_entity")}
yt = cred["EzVFDpaJ0VYd4VSY"]; tgc = cred["XcPiAsINGG1Qqyz5"]
ap = json.dumps(json.loads(c.execute("select nodes from workflow_entity where id='eplMlkxanF3DkrtJ'").fetchone()[0]))
g = lambda k: re.search(k + r": '([^']+)'", ap).group(1)
print(json.dumps({
    "YT_CLIENT_ID": yt["clientId"], "YT_CLIENT_SECRET": yt["clientSecret"], "YT_REFRESH_TOKEN": yt["oauthTokenData"]["refresh_token"],
    "TT_CLIENT_KEY": g("TT_CLIENT_KEY"), "TT_CLIENT_SECRET": g("TT_CLIENT_SECRET"), "TT_REFRESH_TOKEN": g("TT_REFRESH_TOKEN"),
    "IG_TOKEN": g("IG_TOKEN"), "IG_USER_ID": g("IG_USER_ID"), "TG_CHANNEL": g("TG_CHAT"), "TG_CHANNEL_BOT_TOKEN": tgc["accessToken"]}))
EOF
"$PY" - "$R" <<'EOF'
import json, subprocess, sys
s = json.load(open("/tmp/cm_s2.json"))
s["GH_PAT"] = subprocess.check_output(["gh", "auth", "token"], text=True).strip()
for k, v in s.items():
    subprocess.run(["gh", "secret", "set", k, "-R", sys.argv[1]], input=v, text=True, check=True, capture_output=True)
    print("✓", k)
EOF
rm -f /tmp/cm_s2.json

echo "== 3/4 Секреты для бота-кнопок (Cloudflare) → файл cm-bot-secrets.txt"
HS=$(openssl rand -hex 16)
"$PY" - "$R" "$HS" > "$A/cm-bot-secrets.txt" <<'EOF'
import json, re, sqlite3, os, subprocess, sys
c = sqlite3.connect(os.path.expanduser("~/.n8n/database.sqlite"))
js = json.dumps(json.loads(c.execute("select nodes from workflow_entity where id='XvAh0u9iEfr69BVc'").fetchone()[0]))
print("Секреты для Cloudflare-воркера cm-bot (никому не кидай, после настройки удали файл)\n")
for k, v in [("TG_BOT_TOKEN", re.search(r"TG_BOT_TOKEN: '([^']+)'", js).group(1)), ("TG_CHAT_ID", re.search(r"TG_CHAT_ID: '(\d+)'", js).group(1)),
             ("GH_PAT", subprocess.check_output(["gh", "auth", "token"], text=True).strip()), ("GH_REPO", sys.argv[1]), ("HOOK_SECRET", sys.argv[2])]:
    print(f"{k}\n{v}\n")
EOF
chmod 600 "$A/cm-bot-secrets.txt"
echo "файл: $A/cm-bot-secrets.txt"

echo "== 4/4 Проверка: статистика (отчёт придёт в ТГ)"
gh workflow run stats.yml -R "$R"
echo
echo "ГОТОВО. Дальше — воркер cm-bot в Cloudflare (инструкция в чате)."
