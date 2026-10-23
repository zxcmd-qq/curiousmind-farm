#!/bin/bash
# Залить изменения в GitHub + скопировать код бота для Cloudflare.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
cd "$(dirname "$0")"
cp pipeline/workflows/*.yml .github/workflows/
git add -A && git commit -q -m "update $(date +%F)" ; git pull -q --rebase && git push -q && echo "✅ GitHub обновлён" || echo "❌ git push не прошёл"
pbcopy < pipeline/cm-bot-worker.js
echo
echo "📋 Код бота скопирован. Cloudflare → Workers → cm-bot → Edit code → Cmd+A → Cmd+V → Deploy"
echo "⏰ Там же: Settings → Trigger events (Cron) → удали старые 3 и оставь ОДИН:  3 * * * *"
open "https://dash.cloudflare.com/?to=/:account/workers/services/view/cm-bot/production/edit"
echo; read -n 1 -s -r -p "Нажми любую клавишу, чтобы закрыть..."
