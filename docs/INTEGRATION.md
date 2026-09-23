# Интеграция в test-main

Основная инструкция запуска и тестирования находится в [README](../README.md).
Ветка test-main создана от ai-and-logic и объединена с origin/main, содержащим
актуальный frontend. Исходники backend перенесены из origin/codex/backend
(9e9aa6c) без виртуального окружения и pycache.

## Единственный путь расчёта

React → Vite/nginx proxy → backend.main.create_app → WorkflowService →
agent.orchestrator → optional OpenAIExplainer → database.repository → SQLite.

HTTP-контракт из API_CONTRACT.md сохранён. Дополнительные endpoints старого
backend (summary/approve/export) в приложение не включены. Экспорт выполняется
frontend по полученным рекомендациям и после явного подтверждения менеджера.

## Ответственность интеграционных файлов

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
