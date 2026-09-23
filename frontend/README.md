# Frontend FruktAI

Интегрированный React + TypeScript + Tailwind + Recharts интерфейс.
Запуск всего проекта и тестов: [корневой README](../README.md).

Из этой папки: `npm ci`, затем `npm run dev`.
Backend должен работать на 127.0.0.1:8000. Vite проксирует /api и /health;
поэтому CORS-настройки и секреты на frontend не нужны.

`npm test` проверяет отображение API-контракта, фильтры, overrides и CSV.
`npm run build` проверяет TypeScript и production build.
`npm run test:e2e` проверяет работающий стек в браузере (предварительно
`npx playwright install chromium`).

src/api/client.ts вызывает только публичный API.
src/api/presentation.ts преобразует API-поля в модель компонентов без расчёта заказа.
src/mocks/demo.json — сохранённый ответ реального алгоритма на синтетическом CSV,
используется только unit-тестами. В runtime mock fallback отсутствует.
