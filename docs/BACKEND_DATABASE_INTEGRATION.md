# Интеграция FastAPI backend с AI workflow и SQLite

Этот документ предназначен для backend-разработчика. Он описывает интеграцию реальной ветки `codex/backend` с кодом из `ai-and-logic`, не меняя зафиксированный API-контракт.

Главные источники истины:

- [`MVP_SPEC.md`](../MVP_SPEC.md) — алгоритм и границы MVP;
- [`docs/API_CONTRACT.md`](API_CONTRACT.md) — HTTP-контракт;
- [`docs/DATA_CONTRACT.md`](DATA_CONTRACT.md) — шесть входных CSV;
- [`contracts/README.md`](../contracts/README.md) — JSON Schema;
- [`database/schema.sql`](../database/schema.sql) — структура SQLite.

## 1. Текущее состояние backend-ветки

Аудит `origin/codex/backend` выявил несовместимости, которые нужно устранить до merge:

| Сейчас в backend | Требование интеграции |
|---|---|
| `POST /recalculate` принимает multipart и два загружаемых CSV | Принимает JSON `{"dataset":"demo","overrides":[]}` |
| Расчёт выполняется в `backend/calculation.py` | Единственный расчёт выполняет `WorkflowService` |
| Ответ содержит `as_of_date`, `by_supplier`, `warnings` | Ответ строго соответствует `recommendation.schema.json` |
| `/health` возвращает `status` и `service` | Возвращает только `{"status":"ok"}` |
| `/items/{sku}` возвращает только recommendation | Возвращает `sku`, `name`, `history`, `calculation` |
| Результат хранится в `_latest` в памяти | Результат и item history сохраняются в SQLite |
| Используются `sales_demo.csv` и `inventory_demo.csv` | Используются шесть CSV из `data/demo/` |
| В Git добавлены `.venv/` и `__pycache__/` | Эти каталоги удаляются из индекса и игнорируются |
| Нет воспроизводимого `requirements.txt` | Backend фиксирует минимальные зависимости |

`backend/calculation.py` и `backend/services/*` нельзя подключать параллельно с `agent/orchestrator.py`: появятся две разные формулы и разные результаты. Для MVP единственным владельцем числа заказа является `WorkflowService`.

## 2. Целевая схема

```text
POST /api/v1/recalculate
        |
        v
Pydantic request model
        |
        v
WorkflowService.recalculate(dataset, overrides)
        |
        +--> data/demo/*.csv (6 файлов, read-only источник)
        |
        +--> deterministic agent/orchestrator.py
        |
        +--> artifacts/runs/<run_id>.json
        |
        +--> artifacts/fruktai.sqlite
                    |
                    +--> calculation_runs
                    +--> recommendations
                    +--> agent_steps
                    +--> item_history

GET /api/v1/items/{sku}
        |
        +--> WorkflowService.get_item(sku)
                    |
                    +--> SQLite latest completed run
```

Backend остаётся тонким HTTP-адаптером. Он валидирует JSON через Pydantic, вызывает сервис и переводит доменные ошибки в HTTP-коды. Формулу, CSV-парсинг и SQL backend не дублирует.

## 3. Рекомендуемый порядок merge

Работать в backend-ветке:

```bash
git fetch origin
git switch codex/backend
git merge origin/ai-and-logic
```

При конфликте корневого README сохранить ссылки на документы из `ai-and-logic`, затем добавить backend-команды запуска.

До merge убрать окружение и кэш из Git-индекса. Файлы остаются локально, но перестают попадать в коммиты:

```bash
git rm -r --cached .venv
git rm -r --cached backend/__pycache__ backend/services/__pycache__ tests/__pycache__
```

Корневой `.gitignore` из `ai-and-logic` уже исключает эти пути.

## 4. Ожидаемая структура после merge

```text
agent/
  orchestrator.py
  service.py
backend/
  __init__.py
  main.py
  schemas.py
  requirements.txt
contracts/
database/
data/
  demo/
    sales.csv
    inventory.csv
    stockouts.csv
    suppliers.csv
    in_transit.csv
    products.csv
artifacts/                 # создаётся локально, не коммитится
docs/
scripts/
```

Не переносить `agent/` или `database/` внутрь `backend/`. Запускать Uvicorn нужно из корня репозитория, чтобы импорты `from agent ...` и `from database ...` работали одинаково локально и в Docker.

## 5. Конфигурация

Переменные перечислены в [`.env.example`](../.env.example):

| Переменная | Значение по умолчанию | Назначение |
|---|---|---|
| `FRUKTAI_DATA_ROOT` | `data` | Корень наборов данных |
| `FRUKTAI_DATABASE_PATH` | `artifacts/fruktai.sqlite` | Файл SQLite |
| `FRUKTAI_RUNS_DIR` | `artifacts/runs` | JSON-журнал запусков |
| `FRUKTAI_SAFETY_STOCK_DAYS` | `7` | Дни страхового запаса |
| `OPENAI_API_KEY` | — | Секретный API-ключ; нужен только при включённом LLM |
| `OPENAI_MODEL` | `gpt-6-astra` | Модель для текстового объяснения |
| `OPENAI_EXPLANATIONS_ENABLED` | `false` | Включить необязательный explanation layer |
| `OPENAI_TIMEOUT_SECONDS` | `20` | Timeout одного Responses API request |
| `OPENAI_MAX_EXPLANATION_ITEMS` | `20` | Максимум LLM-вызовов на один run |

Backend создаёт сервис один раз при импорте приложения:

```python
from agent import WorkflowService

service = WorkflowService.from_environment()
```

Для MVP запускать один Uvicorn worker. `WorkflowService` сериализует параллельные пересчёты внутри процесса, SQLite использует WAL и `busy_timeout=5000`. Несколько процессов Uvicorn для пятичасового MVP не нужны.

## 6. Pydantic-модели

В `backend/schemas.py` request-модели должны запрещать неизвестные поля:

```python
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthResponse(StrictModel):
    status: Literal["ok"]


class Override(StrictModel):
    sku: str = Field(min_length=1)
    on_hand: int | None = Field(default=None, ge=0)
    in_transit: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_value(self) -> "Override":
        if self.on_hand is None and self.in_transit is None:
            raise ValueError("on_hand or in_transit is required")
        return self


class RecalculateRequest(StrictModel):
    dataset: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    overrides: list[Override] = Field(default_factory=list)


class Summary(StrictModel):
    total_items: int = Field(ge=0)
    total_units_to_order: int = Field(ge=0)
    high_risk_items: int = Field(ge=0)
    anomalies_removed: int = Field(ge=0)
    estimated_stockout_items: int = Field(ge=0)


class Recommendation(StrictModel):
    sku: str
    name: str
    supplier_id: str
    supplier_name: str
    recommended_qty: int = Field(ge=0)
    urgency: Literal["high", "medium", "low"]
    on_hand: int = Field(ge=0)
    in_transit: int = Field(ge=0)
    lead_time_days: int = Field(ge=0)
    avg_daily_demand: float = Field(ge=0)
    forecast_demand: float = Field(ge=0)
    safety_stock: float = Field(ge=0)
    seasonality_factor: float = Field(ge=0)
    growth_factor: float = Field(ge=0)
    stockout_compensation: float = Field(ge=0)
    outlier_units_removed: float = Field(ge=0)
    days_of_cover: float = Field(ge=0)
    reasons: list[str]


class AgentStep(StrictModel):
    step: Literal[
        "load_data",
        "validate_data",
        "detect_outliers",
        "estimate_lost_demand",
        "calculate_recommendations",
        "validate_result",
        "save_result",
    ]
    status: Literal["completed", "warning", "failed"]
    message: str


class RecalculateResponse(StrictModel):
    run_id: str
    generated_at: datetime
    summary: Summary
    recommendations: list[Recommendation]
    agent_steps: list[AgentStep]


class HistoryPoint(StrictModel):
    date: date
    units: float = Field(ge=0)
    is_outlier: bool
    is_stockout: bool
    estimated_lost_units: float = Field(ge=0)


class ItemCalculation(StrictModel):
    recommended_qty: int = Field(ge=0)
    on_hand: int = Field(ge=0)
    in_transit: int = Field(ge=0)
    lead_time_days: int = Field(ge=0)
    avg_daily_demand: float = Field(ge=0)
    forecast_demand: float = Field(ge=0)
    safety_stock: float = Field(ge=0)
    seasonality_factor: float = Field(ge=0)
    growth_factor: float = Field(ge=0)
    stockout_compensation: float = Field(ge=0)
    outlier_units_removed: float = Field(ge=0)
    days_of_cover: float = Field(ge=0)
    reasons: list[str]


class ItemResponse(StrictModel):
    sku: str
    name: str
    history: list[HistoryPoint]
    calculation: ItemCalculation
```

Проверка `Override` продублирована на двух границах: Pydantic возвращает стандартный `422`, а доменная логика не позволяет обойти правило при прямом вызове сервиса.

## 7. FastAPI routes

Минимальный `backend/main.py` под существующую структуру ветки:

```python
from fastapi import FastAPI, HTTPException

from agent import (
    DataValidationError,
    DatabaseError,
    DatasetNotFoundError,
    RecordNotFoundError,
    WorkflowService,
)

from .schemas import (
    HealthResponse,
    ItemResponse,
    RecalculateRequest,
    RecalculateResponse,
)


app = FastAPI(title="FruktAI API", version="1.0.0")
service = WorkflowService.from_environment()


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/api/v1/recalculate", response_model=RecalculateResponse)
def recalculate(request: RecalculateRequest) -> dict:
    try:
        return service.recalculate(
            dataset=request.dataset,
            overrides=[
                value.model_dump(exclude_none=True)
                for value in request.overrides
            ],
        )
    except DatasetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (DataValidationError, DatabaseError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/v1/items/{sku}", response_model=ItemResponse)
def get_item(sku: str) -> dict:
    try:
        return service.get_item(sku)
    except RecordNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except DatabaseError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
```

Не перехватывать общий `Exception` с возвратом пустых рекомендаций. Неожиданная ошибка должна стать `500`, попасть в лог и не выглядеть как успешный расчёт.

Текущие дополнительные routes `/summary`, `/orders/approve`, `/orders/export.csv` не входят в контракт MVP. Рекомендация: убрать их из демонстрационного API до прохождения smoke-test. Если команда решит сохранить их, frontend не должен от них зависеть, а их логика не должна менять рекомендации.

## 8. Подготовка данных

Текущие `data/sales_demo.csv` и `data/inventory_demo.csv` нельзя подключить напрямую: их имена и колонки отличаются от контракта. Нужно подготовить каталог `data/demo/` из шести файлов:

```text
sales.csv:       date,sku,units
inventory.csv:   sku,on_hand
stockouts.csv:   sku,start_date,end_date
suppliers.csv:   supplier_id,supplier_name,lead_time_days
in_transit.csv:  sku,quantity,expected_date
products.csv:    sku,name,supplier_id,active
```

Правила преобразования:

- `sales_demo.quantity` можно перенести в `sales.units`;
- данные товара и поставщика из старого inventory нужно разделить между `products.csv` и `suppliers.csv`;
- `on_hand` остаётся в `inventory.csv`;
- `in_transit` переносится в отдельный файл только при наличии реальной `expected_date`;
- периоды stockout нужно перенести в `stockouts.csv`, не генерируя фиктивные даты;
- если inbound отсутствует для SKU, строку можно не добавлять: сервис использует `0` и объяснение fallback;
- пустой `stockouts.csv` допустим, но заголовок обязателен.

Не придумывать отсутствующие остатки, продажи или даты поставки. Подготовленные данные должны пройти:

```bash
python scripts/check_backend_readiness.py --data-root data --dataset demo
```

Проверка работает на временной БД, не меняет рабочий `artifacts/fruktai.sqlite`, валидирует оба API-ответа и подтверждает влияние override.

## 9. SQLite

SQLite создаётся автоматически при первом пересчёте. Ручная инициализация:

```bash
python scripts/database_cli.py init
```

Полный расчёт без HTTP:

```bash
python scripts/database_cli.py calculate --dataset-path data/demo
```

Просмотр:

```bash
python scripts/database_cli.py show recommendations
python scripts/database_cli.py show suppliers
python scripts/database_cli.py show steps
python scripts/database_cli.py show tables
```

В VS Code открыть `artifacts/fruktai.sqlite` через SQLite viewer. Для демонстрации удобны views:

- `latest_recommendations`;
- `supplier_order_summary`.

Не коммитить `.sqlite`, `artifacts/runs/*.json` или вымышленные результаты. Эти пути уже находятся в `.gitignore`.

## 10. Python-зависимости backend

После удаления старого pandas-расчёта backend достаточно минимального набора:

```text
fastapi>=0.115,<1
uvicorn[standard]>=0.30,<1
httpx>=0.27,<1
pytest>=8,<10
```

`agent/` и `database/` используют только стандартную библиотеку Python. `pandas`, `NumPy` и `python-multipart` не нужны для зафиксированного JSON API. Не удалять их до замены старых routes и прохождения backend-тестов.

## 11. Локальный запуск

Из корня репозитория:

```bash
python -m venv .venv
```

PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
$env:FRUKTAI_DATA_ROOT = "data"
$env:FRUKTAI_DATABASE_PATH = "artifacts/fruktai.sqlite"
$env:FRUKTAI_RUNS_DIR = "artifacts/runs"
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Проверка вручную:

```bash
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/api/v1/recalculate -H "Content-Type: application/json" -d "{\"dataset\":\"demo\",\"overrides\":[] }"
```

## 12. Обязательные проверки перед merge

```bash
python scripts/validate_api_contracts.py
python scripts/test_agent_workflow.py
python scripts/test_database.py
python scripts/test_workflow_service.py
python scripts/test_openai_explainer.py
python scripts/check_backend_readiness.py --data-root data --dataset demo
python -m pytest tests
python scripts/smoke_test.py --base-url http://127.0.0.1:8000
```

Smoke-test должен показать реальное уменьшение `recommended_qty` после увеличения `on_hand`.

## 13. Definition of done

- `/health` возвращает только `{"status":"ok"}`.
- `/recalculate` принимает JSON, а не файлы и form fields.
- Все поля ответа совпадают с `docs/API_CONTRACT.md`.
- Backend не содержит второй активной формулы закупки.
- Все шесть CSV находятся в `data/demo/` и проходят readiness-check.
- Два последовательных расчёта сохраняются как разные `run_id`.
- `/items/{sku}` читает последнюю историю из SQLite.
- Ошибочный dataset возвращает `404`, плохие данные — `422`.
- Неожиданная ошибка не превращается в успешный пустой ответ.
- `.venv`, `__pycache__`, `.sqlite` и `artifacts/` не отслеживаются Git.
- Контрактные, workflow, database, backend и HTTP smoke-тесты проходят.

## 14. Рекомендации по приоритету

1. Сначала заменить HTTP request/response и подключить `WorkflowService`.
2. Затем подготовить шесть реальных CSV и пройти readiness-check.
3. После этого удалить зависимость routes от старого расчёта и выполнить smoke-test.
4. Только после зелёного smoke-test подключать frontend.
5. Не добавлять новые endpoints или модели прогнозирования до завершения основного сценария.
