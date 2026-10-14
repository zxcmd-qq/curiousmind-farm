# Curious Mind — контекст для нового диалога

Я Тим, новичок, MacBook Air M1 (пользователь `mac`), пишу по-русски, отвечай коротко. Автоматический канал коротких видео **Curious Mind**:
TikTok/Instagram **@curiousmind_chiriki**, YouTube «Curious Mind Short» (UCJhS8pn5LqPRJ_EqvW3Sm-g), Telegram **@crpstv**, сайт-линктри **curiousmind.site.je**.

## Где всё работает (Мак больше не нужен)
- **GitHub, публичный репо `zxcmd-qq/curiousmind-farm`** (локальная копия `~/Documents/curiousmind-farm`). Токены лежат в GitHub Secrets.
  - Секреты: `TG_BOT_TOKEN`, `TG_CHAT_ID`, `GEMINI_KEY`, `MPT_CONFIG_B64` (это config.toml MoneyPrinterTurbo в base64), `YT_CLIENT_ID/SECRET/REFRESH_TOKEN`, `TT_CLIENT_KEY/SECRET/REFRESH_TOKEN`, `IG_TOKEN`, `IG_USER_ID`, `TG_CHANNEL`, `TG_CHANNEL_BOT_TOKEN`, `GH_PAT`.
  - Переменная `VOICE`: по умолчанию `gemini:Fenrir-Excitable`. Для ElevenLabs Адама: `gh variable set VOICE -b "elevenlabs:pNInz6obpgDQGcFmaJgB:Adam"` и заново залить `MPT_CONFIG_B64` с ключом.
- **Cloudflare (osttima.workers.dev):**
  - `cm-bot` — webhook бота (кнопки ✅/❌, команды, приём файлов). Секреты: TG_BOT_TOKEN, TG_CHAT_ID, GH_PAT, GH_REPO, HOOK_SECRET; KV-привязка `KV` → `cm-kv`.
  - `cm-comments` — автоответы на комменты в IG (cron раз в 10 мин).
  - `autopost` — данные для дашборда.
- **n8n на Маке выключен**, остался как запасной. Откат на Мак:
  1. `deleteWebhook` бота;
  2. `start-all.command`;
  3. `python3 .patch_gh.py startgen ~/.n8n/database.sqlite` при **выключенном** n8n.
  ⚠️ Базу n8n можно патчить, только когда n8n точно остановлен (`pgrep -fl n8n` пусто). Однажды базу из-за этого повредили, восстанавливали из бэкапа.

## Workflows в репо (`.github/workflows`, исходники в `pipeline/workflows`)
- **generate.yml:** 3 ролика в день, 07/12/17 UTC → факт / квиз / история (Пикабу). Ручной запуск: `gh workflow run generate.yml -f format=facts|quiz|reddit`.
  - `pipeline/run.mjs` гоняет JS-ноды из n8n (`pipeline/nodes/Pick_Format.js`, `Build_Prompt.js`, `Build_Task.js`) → Gemini (с ретраями) → проверка крючка (Gemini переписывает первую фразу, если оценка <8) → MoneyPrinterTurbo API на раннере → баннер (хромакей, если есть) → релиз `videos` (`<id>.mp4` + `<id>.json`) → в ТГ с ✅/❌.
  - Истории идут парами по рейтингу; если Gemini блокирует пару, её выкидывают и берут следующую.
  - Фильтр Пикабу (`pipeline/pikabu_fetch.py`): кровь, травмы, менты, 18+, дети, политика и т.п.
- **decision.yml:** ✅ → `state/approved.log` + `state/publish-queue.txt` (очередь). ❌ на «Часть 1» отменяет часть 2.
- **publish-slot.yml:** 09/15/18 UTC (12/18/21 МСК) публикует 1 ролик из очереди, `pipeline/publish.py`:
  - описание и хештеги через Gemini с правилами площадок плюс фильтр опасных тегов;
  - YouTube Shorts;
  - ТГ-канал (+ викторина для квиза);
  - TikTok в черновики (описание присылает мне);
  - IG Reels через litterbox/uguu/tmpfiles, thumb_offset 1000.
- **weekly.yml:** вс 16 UTC, подборка «N фактов недели» из одобренных → в ТГ с ✅/❌.
- **stats.yml:** вс 18 UTC, статистика YT+IG → Gemini → `state/insights.json` (tips/avoid/cat_weights, учитываются в сценариях) + отчёт в ТГ + продление IG-токена.
- **asset.yml:** файлы из бота:
  - «майнкрафт»/«сатисфай» → фон `bg-<kind>-*.mp4` в релиз `assets`;
  - «баннер» → `banner.mp4/json`, зелень убирается, баннер кладётся под субтитры;
  - «баннер убрать» удаляет. Лимит Telegram — файлы до 20 МБ.
- Состояние в `state/`: used-facts.txt, insights.json, pikabu-cache.json, approved.log, publish-queue.txt, series-queue.json.
- Фоны для историй: релиз `assets` (minecraft.zip, satisfy.zip + bg-*.mp4).

## Бот (команды)
- `/fact`, `/quiz`, `/story` — ролик вне расписания.
- `/now` — опубликовать следующий из очереди.
- `/help` — список команд.
- Видео с подписью «майнкрафт» или «сатисфай» → фоны; «баннер» → баннер.
- Под роликами ✅ (в очередь на прайм-тайм) / ❌.

## Контент и стиль
- **Факты, квизы, истории.** Простой язык, мат в озвучке (в субтитрах звёздочки), темы понятные в СНГ, без политики и Ближнего Востока.
  - Квиз: варианты А/Б/В, пауза с часами и «пик-пик», ответ зелёным.
  - История: карточка Пикабу, фон майнкрафт или сатисфай, сериалы «Часть 1/2».
- **Моушн «хайп»:** цветные плашки с белым текстом и чёрной обводкой; без полоски прогресса; энд-карды «ПОДПИШИСЬ!» / «ЧАСТЬ 2 ЗАВТРА!»; в фактах финал-луп.
- **Голос:** Gemini Fenrir (мужской, женского нет). Жду ElevenLabs (студенческие кредиты).
- **Хештеги:** без криминала, насилия, шок-кликбейта, #fyp.

## Последний шаг (ещё НЕ проверено)
Только что добавлены: луп, проверка крючка, прайм-тайм очередь + `/now`, фоны и баннер через бота. Нужно:
1. Залить:
   ```
   cd ~/Documents/curiousmind-farm && cp pipeline/workflows/*.yml .github/workflows/ && git add -A && git commit -qm "loop, hook, prime-time, assets, banner" && git pull --rebase -q && git push -q
   ```
2. В Cloudflare воркер `cm-bot`: вставить новый `pipeline/cm-bot-worker.js` → Deploy, плюс Bindings → KV `KV` = `cm-kv`.
3. Проверить: `/help`, баннер, пачка фонов, ✅ → «в очереди» → `/now`.

## Идеи на потом
- Английская версия канала (тот же конвейер).
- Автоодобрение, если не нажал за 6 ч.
- Первый коммент от канала на YouTube.
- Темы по Google Trends.
- Формат «ответ на коммент» отложен: из TikTok вопросы автоматически не взять.
