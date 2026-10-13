#!/bin/bash
# Один раз: создаёт репо curiousmind-farm на GitHub, заливает код, секреты и фоны, запускает пробный ролик.
set -e
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
cd "$(dirname "$0")"
NAME=curiousmind-farm
A="$HOME/Documents/n8n-autopost"
PY="$HOME/MoneyPrinterTurbo/.venv/bin/python"

echo "== 1/6 GitHub CLI"
which gh >/dev/null || brew install gh
if ! gh auth status >/dev/null 2>&1; then
  echo "Сейчас откроется браузер — войди в GitHub и вставь код из терминала."
  gh auth login -h github.com -p https -w -s workflow
else
  gh auth refresh -h github.com -s workflow || true
fi
GHUSER=$(gh api user -q .login)
echo "аккаунт: $GHUSER"

echo "== 2/6 Код"
mkdir -p .github/workflows && cp pipeline/workflows/*.yml .github/workflows/
[ -d .git ] || git init -q -b main
git add -A
git -c user.name="$GHUSER" -c user.email="$GHUSER@users.noreply.github.com" commit -q -m "Curious Mind farm" || true
if ! gh repo view "$GHUSER/$NAME" >/dev/null 2>&1; then
  gh repo create "$NAME" --public --source . --remote origin
fi
git remote get-url origin >/dev/null 2>&1 || git remote add origin "https://github.com/$GHUSER/$NAME.git"
gh auth setup-git
git push -u origin main

echo "== 3/6 Секреты (токены берутся с этого Мака, в код не попадают)"
"$PY" - "$A" <<'EOF' > /tmp/cm_secrets.txt
import sqlite3, json, re, os, sys
c = sqlite3.connect(os.path.expanduser("~/.n8n/database.sqlite"))
js = json.dumps(json.loads(c.execute("select nodes from workflow_entity where id='XvAh0u9iEfr69BVc'").fetchone()[0]))
cfg = open(os.path.expanduser("~/MoneyPrinterTurbo/config.toml"), encoding="utf-8").read()
print(re.search(r"TG_BOT_TOKEN: '([^']+)'", js).group(1))
print(re.search(r"TG_CHAT_ID: '(\d+)'", js).group(1))
print(re.search(r'gemini_api_key\s*=\s*"([^"]+)"', cfg).group(1))
EOF
TG=$(sed -n 1p /tmp/cm_secrets.txt); CHAT=$(sed -n 2p /tmp/cm_secrets.txt); GEM=$(sed -n 3p /tmp/cm_secrets.txt); rm -f /tmp/cm_secrets.txt
R="$GHUSER/$NAME"
gh secret set TG_BOT_TOKEN -R "$R" -b "$TG"
gh secret set TG_CHAT_ID -R "$R" -b "$CHAT"
gh secret set GEMINI_KEY -R "$R" -b "$GEM"
base64 -i "$HOME/MoneyPrinterTurbo/config.toml" | tr -d '\n' | gh secret set MPT_CONFIG_B64 -R "$R"
echo "секреты ок"

echo "== 4/6 Фоны для историй (майнкрафт, сатисфай) → релиз assets"
TMP=$(mktemp -d)
(cd "$HOME/Documents/SnippetFarm/фоны/майнкрафт" && zip -q -j -0 "$TMP/minecraft.zip" *.mp4)
(cd "$HOME/Documents/SnippetFarm/фоны/сатисфай" && zip -q -j -0 "$TMP/satisfy.zip" *.mp4)
gh release view assets -R "$R" >/dev/null 2>&1 || gh release create assets -R "$R" -t "Фоны" -n "Фоны для историй" --latest=false
gh release upload assets "$TMP/minecraft.zip" "$TMP/satisfy.zip" -R "$R" --clobber
rm -rf "$TMP"

echo "== 5/6 Доступ Мака к GitHub (для кнопок ✅/❌)"
printf '{"repo": "%s", "token": "%s"}\n' "$R" "$(gh auth token)" > "$A/gh.json"
chmod 600 "$A/gh.json"

echo "== 6/6 Пробный ролик (факт)"
sleep 5
gh workflow run generate.yml -R "$R" -f format=facts
echo
echo "ГОТОВО. Пробный ролик собирается: https://github.com/$R/actions"
echo "Первый раз ~20-30 мин (качается модель Whisper), дальше ~10-15. Ролик придёт в ТГ с ✅/❌."
