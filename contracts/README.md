# API schema index

These JSON Schema documents are the machine-readable form of
[`docs/API_CONTRACT.md`](../docs/API_CONTRACT.md).

| HTTP operation | Payload | Schema |
|---|---|---|
| `GET /health` | response `200` | `health.response.schema.json` |
| `POST /api/v1/recalculate` | request | `recalculate.request.schema.json` |
| `POST /api/v1/recalculate` | response `200` | `recommendation.schema.json` |
| `GET /api/v1/items/{sku}` | response `200` | `item.response.schema.json` |
| Any endpoint | error response | `error.response.schema.json` |

All schemas use JSON Schema Draft 2020-12. Run the dependency-free contract check from the repository root:

```bash
python scripts/validate_api_contracts.py
```

