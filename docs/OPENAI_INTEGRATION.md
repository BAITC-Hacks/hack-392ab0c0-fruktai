# OpenAI explanation integration

OpenAI используется только после завершения детерминированного расчёта. Модель получает готовые факты и возвращает одну строку на русском языке, которая добавляется в массив `reasons`.

Модель не рассчитывает и не изменяет:

- `recommended_qty`;
- остаток и товар в пути;
- forecast и safety stock;
- urgency;
- supplier/SKU;
- summary и журнал шагов.

## Configuration

Секрет хранится только в локальном `.env` или в переменных окружения backend:

```env
OPENAI_API_KEY=sk-your-real-key
OPENAI_MODEL=gpt-6-astra
OPENAI_EXPLANATIONS_ENABLED=true
OPENAI_TIMEOUT_SECONDS=20
OPENAI_MAX_EXPLANATION_ITEMS=20
```

`.env` уже исключён через `.gitignore`. Никогда не добавлять настоящий ключ в `.env.example`, frontend-переменные, Dockerfile, README, логи или GitHub Actions output.

`gpt-6-astra` выбран как quality-first fallback. Во время разработки официальный каталог моделей не удалось загрузить через доступный канал, поэтому доступность этой модели зависит от API-проекта. Если connection-check вернёт `404`, установить в `OPENAI_MODEL` доступный текстовый model ID из [официального каталога OpenAI](https://developers.openai.com/api/docs/models).

## Startup

Backend создаёт сервис обычным способом:

```python
from agent import WorkflowService

service = WorkflowService.from_environment()
```

Если `OPENAI_EXPLANATIONS_ENABLED=false`, ключ не требуется и запросов в OpenAI нет. Если значение `true`, отсутствие ключа останавливает backend при старте с понятной ошибкой конфигурации.

PowerShell:

```powershell
python -m uvicorn backend.main:app --reload --env-file .env
```

## Data flow and safety boundary

1. `agent/orchestrator.py` рассчитывает полный response.
2. Оркестратор валидирует формулу.
3. `OpenAIExplainer` отправляет модели только факты одной recommendation.
4. Из ответа принимается только plain text до 500 символов.
5. Текст добавляется как `AI-пояснение: ...` в `reasons`.
6. Все остальные поля сравниваются с исходным расчётом.
7. Enriched response и item details сохраняются в SQLite.

Модель не возвращает JSON для слияния с recommendation. Это намеренно исключает возможность подмены количества через model output.

## Controlled fallback

При timeout, сетевой ошибке, `401`, `404`, `429`, ошибке модели или неожиданном формате ответа:

- рекомендация остаётся успешной;
- исходные детерминированные `reasons` сохраняются;
- дальнейшие платные LLM-вызовы для текущего run прекращаются;
- в server log записывается предупреждение без API-ключа;
- количество заказа не меняется.

## Cost and latency controls

Сейчас выполняется не более одного Responses API request на одну recommendation. Ограничение на один run задаёт:

```env
OPENAI_MAX_EXPLANATION_ITEMS=20
```

Для демо с шестью SKU это не более шести вызовов. Чтобы временно отключить расходы:

```env
OPENAI_EXPLANATIONS_ENABLED=false
```

Для основного MVP детерминированные причины уже достаточны, поэтому LLM не является обязательной зависимостью.

## Tests

Offline-тест не использует ключ и не расходует API budget:

```bash
python scripts/test_openai_explainer.py
```

Он проверяет:

- успешное добавление текста;
- неизменность всех расчётных полей;
- fallback при ошибке OpenAI;
- сохранение AI-текста в SQLite item detail.

Один реальный API-вызов для проверки ключа и модели:

```bash
python scripts/check_openai_connection.py --env-file .env --model gpt-6-astra
```

Скрипт не печатает ключ. Он выводит только model ID и полученное объяснение.

## API contract

Новые поля не добавляются. AI-текст является дополнительным элементом уже существующего массива `reasons`, поэтому `docs/API_CONTRACT.md` и JSON Schema не меняются.

