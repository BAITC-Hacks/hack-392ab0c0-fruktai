# Backend + SQLite: интеграция выполнена в test-main

Запуск и полный прогон описаны в [корневом README](../README.md).
Это актуальная инструкция для backend-разработчика; прежний план миграции
multipart API заменён работающей JSON-интеграцией.

## Подключение

backend/main.py создаёт FastAPI через create_app(). На startup создаётся
WorkflowService.from_environment() и инициализируется database/schema.sql.
Маршруты вызывают service.recalculate(dataset, overrides) и service.get_item(sku).

Для теста можно передать изолированный сервис в create_app(service).
Пример: tests/test_integrated_api.py.

## Конфигурация

FRUKTAI_DATA_ROOT=data, FRUKTAI_DATABASE_PATH=artifacts/fruktai.sqlite,
FRUKTAI_RUNS_DIR=artifacts/runs, FRUKTAI_SAFETY_STOCK_DAYS=7.
OpenAI-переменные описаны в OPENAI_INTEGRATION.md; секрет только на сервере.

Сервис сериализует расчёты внутри одного процесса. Запускать один Uvicorn worker.
SQLite использует WAL и busy_timeout. Это локальный MVP, не multi-worker production.

## Данные и результаты

Шесть CSV из DATA_CONTRACT.md валидируются алгоритмом до загрузки в SQLite.
Отрицательные остатки и некорректные overrides возвращают HTTP 422.
Отсутствующий dataset/SKU — 404. Сбой хранилища — 500 без раскрытия пути/SQL.
GET items читает сохранённый результат и работает после перезапуска.

Полезные таблицы: calculation_runs, recommendations, item_history, agent_steps,
run_overrides. Полезные views: latest_recommendations, supplier_order_summary.

CSV остаются источником, изменения остатков через API сохраняются как overrides
конкретного run. Исходные CSV не изменяются.

## Проверки

```bash
python -m pytest tests -q
python scripts/test_full_stack.py
python scripts/test_database.py
python scripts/test_workflow_service.py
python scripts/smoke_test.py --base-url http://127.0.0.1:8000
```

Первая группа проверок изолирует БД; smoke_test работает с указанным живым API
и создаёт реальные записи. Для просмотра откройте artifacts/fruktai.sqlite в VS Code.

## Сохранённые наработки backend

calculation.py и services/ сохранены с оригинальными unit-тестами.
Они не импортируются публичным HTTP-путём. Единственный активный расчёт:
agent/orchestrator.py. Не подключать обе формулы одновременно.
