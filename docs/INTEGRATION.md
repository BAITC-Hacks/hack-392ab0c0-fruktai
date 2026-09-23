# Интеграция в test-main

Основная инструкция запуска и тестирования находится в [README](../README.md).
Ветка test-main создана от ai-and-logic и объединена с origin/main, содержащим
актуальный frontend. Исходники backend перенесены из origin/codex/backend
(9e9aa6c) без виртуального окружения и pycache.

## Единственный путь расчёта

React → Vite/nginx proxy → backend.main.create_app → WorkflowService →
agent.orchestrator → optional OpenAIExplainer → database.repository → SQLite.

Существующие поля HTTP-контракта сохранены; версия 1.1.0 добавляет импорт,
метаданные, шаблон и экспорт сохранённого run_id. Старые альтернативные маршруты
backend (summary/approve/export) не подключены. Новый экспорт выполняется
backend/exports.py по SQLite после подтверждения в интерфейсе.

Вход: React → backend/imports.py → нормализация/валидация → artifacts/imports
и source_imports в SQLite → существующий WorkflowService. Реальный формат 1С
согласуется отдельно; сейчас доступен файловый обмен, не OData.
Подробности: [INPUT_OUTPUT.md](INPUT_OUTPUT.md).

## Ответственность интеграционных файлов

- backend/imports.py, backend/exports.py — граница файлового обмена; PDF без OCR.
- backend/main.py — HTTP, запуск SQLite, перевод ошибок в 404/422/500.
- backend/schemas.py — Pydantic wire models; прежние внутренние модели сохранены.
- agent/service.py — расчёт, необязательное AI-обогащение, сохранение.
- database/ — единая БД из ветки ai-and-logic.
- frontend/src/api/ — API-клиент и преобразование для компонентов.
- scripts/run_local.py — общий локальный запуск; AI включается флагом --ai.
- scripts/test_full_stack.py — HTTP-прогон и перезапуск с временной БД.
- frontend/e2e/workflow.spec.ts — браузерный тест до скачивания CSV.
- docker-compose.yml — общий запуск backend и frontend с постоянной БД.

## Что проверять при следующем merge

Запустить pytest, test_full_stack, существующие script-тесты, npm test/build,
затем test:e2e при работающем стеке. Не менять поля API без обновления контракта.
Не подключать второй расчёт из backend/calculation.py к публичным маршрутам.
Не коммитить .env, sqlite, artifacts, node_modules или виртуальное окружение.
