# Team integration handoff

## Frozen interfaces

The MVP integration boundary is version `1.0.0`. Only the Tech Lead changes it, starting with `docs/API_CONTRACT.md`.

Backend owner must use:

- `MVP_SPEC.md` for deterministic calculation policy and fallbacks;
- `docs/API_CONTRACT.md` for Pydantic request/response models and HTTP behavior;
- `docs/DATA_CONTRACT.md` for CSV parsing and validation;
- `contracts/recommendation.schema.json` for the recalculation response shape;
- `agent.run_workflow` as the calculation entry point;
- `scripts/test_agent_workflow.py` for local workflow regression;
- `scripts/smoke_test.py` for integrated API acceptance.

Frontend owner must use:

- `docs/API_CONTRACT.md` for TypeScript types and API calls;
- `contracts/recommendation.schema.json` as the machine-readable response reference;
- only `GET /health`, `POST /api/v1/recalculate`, and `GET /api/v1/items/{sku}`;
- `dataset: "demo"` and the documented override structure.

The frontend must not invent fields. Until the backend is available, it may use exactly one mock response matching `contracts/recommendation.schema.json` and must remove or disable that mock at integration time.

## Backend integration

Recommended function-level adapter:

```python
from agent import DataValidationError, run_workflow

result = run_workflow(
    dataset_path="data/demo",
    overrides=[override.model_dump(exclude_none=True) for override in request.overrides],
)
```

Map `DataValidationError` to HTTP `422` and a missing dataset to HTTP `404`. Do not catch a calculation failure and return placeholder recommendations.

The backend owns:

- FastAPI routes and Pydantic models;
- locating the requested dataset under a fixed data root;
- safe dataset-name validation (no absolute paths or `..`);
- storage of the latest successful result for item drill-down;
- serialization of item history for `GET /api/v1/items/{sku}`;
- `backend/Dockerfile` and Python dependencies.

The demo data owner must provide all six files under `data/demo/`. At least one SKU must have a positive baseline recommendation so the override smoke test is meaningful.

## Frontend integration

The frontend owns:

- dashboard layout and charts;
- grouping recommendations by `supplier_id`/`supplier_name`;
- urgency filters and summary cards;
- the SKU drill-down using the item endpoint;
- editable `on_hand` and `in_transit` controls that send overrides;
- loading, empty, and API error states;
- `frontend/Dockerfile` and build configuration.

Calculations and fallback logic must not be duplicated in TypeScript.

## Merge gate

For each integration merge:

1. Review the diff for contract field changes.
2. Run `python scripts/test_agent_workflow.py`.
3. Start backend and frontend using their documented commands.
4. Run `python scripts/smoke_test.py --base-url http://localhost:8000`.
5. Verify the dashboard uses the returned run and override result.
6. Only then merge into the shared integration branch.

