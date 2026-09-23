# FruktAI

FruktAI is a HackAlem AI hackathon MVP that creates transparent supplier-order recommendations from sales, inventory, inbound-stock, stockout, product, and supplier CSV files.

The order quantity is deterministic:

```text
recommended_qty = max(
  0,
  forecast_demand_during_lead_time
  + safety_stock
  - on_hand
  - in_transit
)
```

An LLM never determines this value.

## Source of truth

- [MVP scope and algorithm](MVP_SPEC.md)
- [HTTP API contract](docs/API_CONTRACT.md)
- [CSV data contract](docs/DATA_CONTRACT.md)
- [Team integration handoff](docs/INTEGRATION.md)
- [Backend + SQLite integration guide](docs/BACKEND_DATABASE_INTEGRATION.md)
- [Optional OpenAI explanation layer](docs/OPENAI_INTEGRATION.md)
- [Response JSON Schema](contracts/recommendation.schema.json)

## Repository layout

```text
agent/       deterministic workflow and backend API client
contracts/   machine-readable wire contracts
database/    optional SQLite schema and ER diagram for inspection
docs/        API, data, and integration documentation
scripts/     workflow regression and HTTP smoke tests
backend/     FastAPI service (backend owner)
frontend/    React dashboard (frontend owner)
data/demo/   six contract-compliant demo CSV files (data/backend owner)
```

## Available now

The calculation workflow uses only the Python standard library. From the repository root:

```bash
python scripts/validate_api_contracts.py
python scripts/test_agent_workflow.py
python scripts/test_database.py
python scripts/test_workflow_service.py
python scripts/test_openai_explainer.py
```

The test creates an isolated temporary dataset, executes all seven workflow steps, verifies outlier and stockout handling, checks negative-inventory validation, persists a run, and confirms that increasing `on_hand` lowers the recommendation.

## Integrated API check

After the backend owner starts the FastAPI service on port `8000`:

```bash
python scripts/smoke_test.py --base-url http://localhost:8000
```

This checks `/health`, both required API resources, response fields, workflow order, and a real recalculation with an inventory override. It does not return mock success results when the backend is unavailable.

## Full application startup

Until `backend/` and `frontend/` are merged, use each owner's documented development command. The Tech Lead will add or validate `docker-compose.yml` only after both real Dockerfiles exist; the repository will not claim a non-runnable Compose setup.

Integration rules and the exact owner handoff are in [docs/INTEGRATION.md](docs/INTEGRATION.md).

## Optional SQLite inspection

CSV remains the MVP source of truth. To create a local SQLite database that can be opened in Visual Studio Code:

```bash
python scripts/database_cli.py init
python scripts/database_cli.py calculate --dataset-path data/demo
python scripts/database_cli.py show recommendations
```

The generated file is `artifacts/fruktai.sqlite`. Database structure and viewing instructions are in [database/ER_DIAGRAM.md](database/ER_DIAGRAM.md).

## Optional OpenAI explanations

OpenAI may add a short natural-language element to `reasons` after calculation. It cannot change `recommended_qty` or any other calculation field. Configuration, fallback behavior, cost controls, and tests are documented in [docs/OPENAI_INTEGRATION.md](docs/OPENAI_INTEGRATION.md).

## Backend handoff

The current backend branch uses a different upload-based API and calculation model. Before merging it with this branch, follow [docs/BACKEND_DATABASE_INTEGRATION.md](docs/BACKEND_DATABASE_INTEGRATION.md). The guide contains the exact Pydantic models, FastAPI routes, environment variables, six-file data migration, SQLite commands, error mapping, tests, and merge checklist.
