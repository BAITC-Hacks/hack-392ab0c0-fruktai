# FruktAI — интегрированный предфинальный MVP

Ветка `test-main` объединяет frontend команды, FastAPI, вашу AI-логику и SQLite.
Пользователь открывает таблицу рекомендаций, видит причины и историю продаж,
изменяет остаток / товар в пути, получает пересчёт и экспортирует CSV после проверки.

Число заказа рассчитывает алгоритм:

```text
ceil(max(0, forecast_demand + safety_stock - on_hand - in_transit))
```

OpenAI может добавить пояснение. Ошибка OpenAI не отменяет расчёт.
Все экранные рекомендации загружаются из API. Файл mock используется только тестами.

## Быстрый запуск на Windows

Нужны Python 3.10+ и Node.js 22+. Команды выполнять из корня репозитория:

```powershell
git fetch origin
git switch test-main
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
npm --prefix frontend ci
.\.venv\Scripts\python.exe scripts/run_local.py
```

Оставьте терминал открытым. Остановка обоих серверов — Ctrl+C.

- Интерфейс: http://127.0.0.1:5173
- Swagger: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

`run_local.py` запускает оба процесса и по умолчанию **отключает платные AI-вызовы**.
Существующий `.env` перезаписывать не нужно. SQLite создаётся автоматически.

Для macOS/Linux: вместо `.\.venv\Scripts\python.exe` используйте `.venv/bin/python`.

## Запуск с OpenAI

Ключ должен быть только в корневом `.env`:

```env
OPENAI_API_KEY=ваш_ключ
OPENAI_MODEL=gpt-6-astra
OPENAI_EXPLANATIONS_ENABLED=true
```

После остановки обычного запуска:

```powershell
.\.venv\Scripts\python.exe scripts/run_local.py --ai
```

Один пересчёт вызывает одну пакетную AI-операцию с ограниченными повторами.
При отказе провайдера сохраняются детерминированные причины; подробности видны
в серверном логе. Наличие ответа HTTP 200 само по себе не доказывает работу LLM.
Успешное AI-пояснение начинается с `AI-пояснение:`.

Полный live-тест AI → HTTP → SQLite на временной БД (один платный пакетный
запрос по учебным данным): `python scripts/test_ai_integration.py`.
Тест требует корневой `.env` с ключом и явно завершается ошибкой при fallback.

Настройки лимитов и fallback: [OpenAI integration](docs/OPENAI_INTEGRATION.md).
Описание входа и выхода: [AI contract](docs/AI_API_CONTRACT.md).

## Полный автоматический прогон

В отдельном терминале из корня:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe scripts/test_full_stack.py
.\.venv\Scripts\python.exe scripts/validate_api_contracts.py
.\.venv\Scripts\python.exe scripts/test_agent_workflow.py
.\.venv\Scripts\python.exe scripts/test_database.py
.\.venv\Scripts\python.exe scripts/test_workflow_service.py
.\.venv\Scripts\python.exe scripts/test_openai_explainer.py
npm --prefix frontend test
npm --prefix frontend run build
```

`test_full_stack.py` сам запускает настоящий HTTP-сервер на свободном порту,
выполняет health → расчёт → изменение остатка → историю товара, затем перезапускает
сервер и проверяет сохранность результата в SQLite. Использует временную БД,
не меняет рабочую БД и не вызывает OpenAI.

Для проверки уже запущенного приложения, включая Vite-прокси:

```powershell
.\.venv\Scripts\python.exe scripts/smoke_test.py --base-url http://127.0.0.1:5173
```

Smoke-test создаёт два настоящих расчёта в рабочей БД; последний содержит override.
Нажмите «Обновить данные» в UI, чтобы вернуться к исходным CSV.

Браузерный прогон при работающем `run_local.py`:

```powershell
cd frontend
npx playwright install chromium
npm run test:e2e
cd ..
```

Проверяет таблицу, открытие товара и графика, пересчёт, чтение из API/БД и
скачивание CSV. Для установленного Chrome можно задать
`$env:PLAYWRIGHT_CHANNEL = "chrome"` и пропустить загрузку Chromium.

## Демонстрация за две минуты

1. Откройте http://127.0.0.1:5173 — загрузятся 6 SKU.
2. Включите «По поставщикам», откройте любой товар с ненулевым заказом.
3. Посмотрите формулу, причины и график истории.
4. Введите остаток `10000`, нажмите «Пересчитать через API».
   Рекомендация станет нулевой, отобразятся значения до / после.
5. Закройте карточку. Во вкладке «Данные» раскройте «Ход анализа»:
   там настоящий `run_id` и семь выполненных шагов.
6. Нажмите «Проверить заказ», подтвердите проверку, скачайте CSV.
   Отправка поставщику не выполняется.
7. «Обновить данные» сбрасывает поправки и заново считает исходный набор.

## Данные и БД

[data/demo/README.md](data/demo/README.md) описывает **синтетический** учебный набор:
56 дней, стабильный спрос, недельный рисунок, рост, stockout, выброс и поставка в пути.
Это не данные партнёра и не готовый расчёт.

Источники: `data/demo/{sales,inventory,stockouts,suppliers,in_transit,products}.csv`.
CSV не изменяются при пересчёте; override относится только к текущему запуску.
Внутри UI поправки нескольких SKU накапливаются до «Обновить данные».

- `artifacts/fruktai.sqlite` — SQLite с расчётами, причинами, историей и журналом.
- `artifacts/runs/` — JSON исходного детерминированного этапа, до AI-обогащения.
- Структура: [database/schema.sql](database/schema.sql).
- Для VS Code откройте SQLite через SQLite Viewer; полезны
  `latest_recommendations`, `supplier_order_summary`, `calculation_runs`.
- Ключи, БД, журналы, виртуальное окружение и node_modules исключены из Git.

## Docker Compose

Альтернатива локальному запуску, когда работает Docker Desktop:

```powershell
docker compose up --build -d
docker compose ps
python scripts/smoke_test.py --base-url http://127.0.0.1:5173
docker compose logs --tail=100 backend
docker compose down
```

Те же адреса: UI 5173, API 8000. Не запускайте локальные процессы одновременно
на этих портах. Каталог `./artifacts` примонтирован: БД остаётся после остановки.

Compose читает корневой `.env`. Для прогона без OpenAI:
`$env:OPENAI_EXPLANATIONS_ENABLED = "false"` перед `docker compose up`.
Для включения задайте `true` и выполните `docker compose up -d --force-recreate backend`.
Ключ передаётся только backend и не попадает в frontend build.

## Архитектура и границы интеграции

```text
React :5173 -> Vite/nginx proxy -> FastAPI :8000
                                    |
                              WorkflowService
                              /             \
                       CSV + алгоритм     OpenAI (optional)
                              \             /
                                  SQLite
```

Публичные маршруты: `GET /health`, `POST /api/v1/recalculate`,
`GET /api/v1/items/{sku}`. Контракт не переименован:
[API](docs/API_CONTRACT.md), [CSV](docs/DATA_CONTRACT.md), [JSON Schema](contracts/README.md).

В API работает только `agent/orchestrator.py`. Исходные
`backend/calculation.py` и `backend/services/` сохранены вместе с тестами как
наработка backend-участника; HTTP их не использует. Для запуска достаточно
`backend/requirements.txt`; pandas/NumPy нужны только для тестов этих наработок.

Происхождение: AI/БД — `83e19ff`, frontend/main — `35ee99e`
(frontend `0c53176`), исходники backend — `9e9aa6c`.
Backend перенесён выборочно: его `.venv`, pycache и конфликтующая реализация
`database/` не включались. Общая БД сохранена из AI-ветки.

Предфинальные ограничения: один процесс API, CSV-источник, локальный расчёт
сезонности по последним неделям, без полноценного годового прогноза и
клиентского анализа разовых транзакций. Категория, физическая единица и ETA
отсутствуют в публичном контракте; UI не выдаёт их за известные.
Массовая интеграция 1С и автоматическая отправка заказов не реализованы.

Проверено при интеграции: 22 pytest-теста, HTTP-прогон с перезапуском SQLite,
контрактные/script-тесты, frontend unit/build, браузерный E2E через установленный
Chrome и реальный OpenAI-прогон на шести SKU.
Compose прошёл проверку конфигурации; запуск контейнеров не проверен, поскольку
Docker daemon на машине не был запущен.
