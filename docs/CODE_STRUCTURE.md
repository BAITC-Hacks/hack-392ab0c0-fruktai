# Структура кода и правила сопровождения

Рефакторинг сохраняет HTTP-контракт, схемы SQLite и формулу расчёта.
Цель — разделить обязанности, а не уменьшить число строк сжатием кода.

## Карта модулей

| Область | Точка входа | Реализация |
|---|---|---|
| HTTP | backend/main.py | Маршруты и перевод ошибок; бизнес-логики в обработчиках нет |
| Импорт | backend/imports.py | Публикация снимка; file_exchange/normalization.py — поля/ячейки, parsers.py — форматы |
| Экспорт | backend/exports.py | Чтение сохранённого run_id и безопасный CSV/XLSX |
| Расчёт | agent/orchestrator.py | Порядок шагов и журнал; алгоритмы в agent/workflow/ |
| AI-пояснения | agent/openai_explainer.py | Обогащение и fallback; explanation_contract.py — проверка входа, выхода и неизменности чисел |
| SQLite | database/repository.py | Совместимый публичный фасад; реализации разделены ниже |
| React | frontend/src/App.tsx | Только сборка оболочки, заголовка, экранов и диалогов |
| Состояние UI | frontend/src/hooks/useWorkspace.ts | Запросы, защита от устаревшего ответа, фильтры, выбор, черновики и пересчёт |
| Стили | frontend/src/index.css | Порядок импортов тематических файлов styles/ |

## Детерминированный workflow

- models.py — структуры состояния, ошибки и обязательные CSV.
- primitives.py — преобразования типов, проверка значений и числовые помощники.
- data.py — чтение CSV, связи между справочниками и явные overrides.
- demand.py — выбросы и компенсация упущенного спроса.
- recommendations.py — потребность, срочность, причины.
- results.py — ответ API, история товара и проверка результата.

ReplenishmentOrchestrator, run_workflow и run_workflow_with_details остаются
доступны через прежние импорты. Оркестратор не вызывает LLM для вычисления заказа.

## SQLite

- connection.py — соединение, транзакция, схема и исключения.
- validation.py — проверка значений источников и сохраняемых данных.
- sources.py — валидация и синхронизация шести исходных таблиц.
- calculations.py — сохранение запуска, поправок, рекомендаций и истории.
- queries.py — запросы для интерфейса и локального просмотра.
- repository.py и __init__.py сохраняют внешние имена функций.

Не добавлять вторую базу, не менять схему ради перемещения Python-функций.

## Интерфейс

components/workspace/ содержит оболочку, заголовок, выбор экрана,
закупочную очередь и диалоги. Каждый компонент отвечает за одну область.
Тип WorkspaceController выводится из useWorkspace: поля состояния не
дублируются вручную в нескольких интерфейсах.

components/item/SalesHistory.tsx самостоятельно загружает историю конкретного
run_id. RecommendationDetails отвечает за формулу и what-if.
Остальные компоненты — таблица, фильтры, показатели, импорт, экспорт и журнал.

styles/ разделён на foundation, sidebar, shell, queue-controls, table,
analytics, workflow, sources, drawer, scenario, review, states, responsive
и mobile. Порядок импортов в index.css сохраняет каскад.

Исходные backend/calculation.py и backend/services/ сохранены как наработка
участника; публичный API их не использует. При чистке выполнено форматирование
и удаление неиспользуемых импортов, без подмены рабочего алгоритма.

## Проверки перед коммитом

Все команды из корня репозитория, каждая отдельно:

```powershell
.\.venv\Scripts\python.exe scripts/check_code_size.py
.\.venv\Scripts\python.exe -m ruff check agent backend database scripts tests
.\.venv\Scripts\python.exe -m ruff format --check agent backend database scripts tests
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe scripts/test_full_stack.py
.\.venv\Scripts\python.exe scripts/validate_api_contracts.py
npm --prefix frontend run format:check
npm --prefix frontend test
npm --prefix frontend run build
```

Для автоформатирования: ruff format без --check и npm --prefix frontend run format.
Ruff и Prettier — только инструменты разработки, не зависимости приложения.

При запущенном стеке: npm --prefix frontend run test:e2e.
Браузерные тесты проверяют импорт, пересчёт, экспорт, мобильный экран,
фокус после закрытия панели и восстановление после ошибки API.

Лимит: 350 физических строк, включая пустые строки и комментарии, для Python,
TS/TSX, CSS, SQL и JS-скриптов. Зависимости, сборки, данные и lock-файлы не
проверяются. Превышение устраняется выделением ответственности, не минификацией.
