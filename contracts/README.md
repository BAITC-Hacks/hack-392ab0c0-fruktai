# API schema index

These JSON Schema documents are the machine-readable form of the public
[`docs/API_CONTRACT.md`](../docs/API_CONTRACT.md) and the internal
[`docs/AI_API_CONTRACT.md`](../docs/AI_API_CONTRACT.md).

| HTTP operation | Payload | Schema |
|---|---|---|
| `GET /health` | response `200` | `health.response.schema.json` |
| `POST /api/v1/recalculate` | request | `recalculate.request.schema.json` |
| `POST /api/v1/recalculate` | response `200` | `recommendation.schema.json` |
| `GET /api/v1/items/{sku}` | response `200` | `item.response.schema.json` |
| Any endpoint | error response | `error.response.schema.json` |
| Import dataset / dataset metadata | response | `import.response.schema.json` |

| AI boundary | Payload | Schema |
|---|---|---|
| OpenAI explanation stage | sanitized domain input | `ai-explanation.input.schema.json` |
| OpenAI explanation stage | strict model output | `ai-explanation.output.schema.json` |

All schemas use JSON Schema Draft 2020-12. Run the dependency-free contract check from the repository root:

```bash
python scripts/validate_api_contracts.py
```
