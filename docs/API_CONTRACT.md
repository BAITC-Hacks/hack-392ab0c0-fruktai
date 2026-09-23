# FruktAI API contract

Contract version: `1.1.0`
Base path: `/api/v1`  
Content type: `application/json`

Machine-readable schema index: [`contracts/README.md`](../contracts/README.md).

This document is the source of truth for backend, frontend, agent integration, and smoke tests. Contract fields must not be renamed or removed without updating this document first and notifying both owners.

## Common rules

- Datetimes are UTC ISO 8601 strings, for example `2026-09-23T10:15:30Z`.
- Quantities are expressed in base product units.
- `recommended_qty` is a non-negative integer.
- Calculated decimal fields are finite JSON numbers rounded to two decimal places.
- `urgency` is one of `high`, `medium`, or `low`.
- Unknown JSON request fields are rejected.
- Validation errors use FastAPI's standard HTTP `422` response.
- Missing datasets or SKUs return HTTP `404`.
- Invalid source data returns HTTP `422`; unexpected failures return HTTP `500` and must not contain fabricated recommendations.

## `GET /health`

Checks whether the backend process is available.

Response `200`:

```json
{
  "status": "ok"
}
```

Schema: [`contracts/health.response.schema.json`](../contracts/health.response.schema.json).

## `POST /api/v1/recalculate`

Runs the deterministic workflow for a named dataset. Overrides apply only to this run and do not modify source CSV files.

Request:

```json
{
  "dataset": "demo",
  "overrides": [
    {
      "sku": "SKU-001",
      "on_hand": 25,
      "in_transit": 20
    }
  ]
}
```

Request fields:

| Field | Type | Required | Rules |
|---|---|---:|---|
| `dataset` | string | yes | Non-empty dataset directory name; supports `demo` and IDs returned by the import route. |
| `overrides` | array | no | Defaults to `[]`; at most one entry per SKU. |
| `overrides[].sku` | string | yes | Must exist in `products.csv`. |
| `overrides[].on_hand` | integer | no | `>= 0`; omitted value uses CSV data. |
| `overrides[].in_transit` | integer | no | `>= 0`; omitted value uses CSV data. |

At least one of `on_hand` or `in_transit` is required in each override. Dataset names may contain only Latin letters, digits, `_`, and `-`; path fragments are rejected.

Request schema: [`contracts/recalculate.request.schema.json`](../contracts/recalculate.request.schema.json).

Response `200`:

```json
{
  "run_id": "string",
  "generated_at": "2026-09-23T10:15:30Z",
  "summary": {
    "total_items": 0,
    "total_units_to_order": 0,
    "high_risk_items": 0,
    "anomalies_removed": 0,
    "estimated_stockout_items": 0
  },
  "recommendations": [
    {
      "sku": "string",
      "name": "string",
      "supplier_id": "string",
      "supplier_name": "string",
      "recommended_qty": 0,
      "urgency": "high",
      "on_hand": 0,
      "in_transit": 0,
      "lead_time_days": 0,
      "avg_daily_demand": 0.0,
      "forecast_demand": 0.0,
      "safety_stock": 0.0,
      "seasonality_factor": 1.0,
      "growth_factor": 1.0,
      "stockout_compensation": 0.0,
      "outlier_units_removed": 0.0,
      "days_of_cover": 0.0,
      "reasons": ["string"]
    }
  ],
  "agent_steps": [
    {
      "step": "load_data",
      "status": "completed",
      "message": "Loaded demo dataset"
    }
  ]
}
```

Summary semantics:

| Field | Meaning |
|---|---|
| `total_items` | Number of active SKUs evaluated. |
| `total_units_to_order` | Sum of `recommended_qty`. |
| `high_risk_items` | Number of recommendations with `urgency = high`. |
| `anomalies_removed` | Number of daily SKU observations marked as outliers. |
| `estimated_stockout_items` | Number of SKUs with positive `stockout_compensation`. |

`days_of_cover` is `(on_hand + in_transit) / avg_daily_demand`. When average demand is zero it is `0.0`, accompanied by a reason; JSON infinity is forbidden.

The success response is formally defined by [`contracts/recommendation.schema.json`](../contracts/recommendation.schema.json).

## `GET /api/v1/items/{sku}`

Returns drill-down data from the latest run for a SKU. If no run exists yet, the backend may calculate the default `demo` dataset before returning.

Response `200`:

```json
{
  "sku": "SKU-001",
  "name": "Apples Gala",
  "history": [
    {
      "date": "2026-09-01",
      "units": 12.0,
      "is_outlier": false,
      "is_stockout": false,
      "estimated_lost_units": 0.0
    }
  ],
  "calculation": {
    "recommended_qty": 48,
    "on_hand": 25,
    "in_transit": 20,
    "lead_time_days": 7,
    "avg_daily_demand": 8.0,
    "forecast_demand": 56.0,
    "safety_stock": 56.0,
    "seasonality_factor": 1.0,
    "growth_factor": 1.0,
    "stockout_compensation": 0.0,
    "outlier_units_removed": 0.0,
    "days_of_cover": 5.63,
    "reasons": ["Order covers lead-time demand and safety stock"]
  }
}
```

The calculation object deliberately reuses names and meanings from the recommendation response. Frontend code must not infer or invent additional business fields.

Response schema: [`contracts/item.response.schema.json`](../contracts/item.response.schema.json).

## Error responses

Application errors use `{"detail": "message"}`. FastAPI request-validation errors keep the standard `detail` array. Both forms are defined by [`contracts/error.response.schema.json`](../contracts/error.response.schema.json).

## File exchange and input/output (1.1.0, additive)

Existing recommendation fields and the three existing routes remain compatible.
New routes are shared by the frontend and the 1C file-exchange adapter:

- `POST /api/v1/datasets/import`: multipart `files[]` (repeated field `files`),
  `anonymized=true`, optional `warehouse_id`. Supports CSV/TSV, XLSX, XLS, JSON,
  and text-based table PDFs. Maximum 12 files, 10 MiB each, 30 MiB total,
  50,000 data rows total, 50 PDF pages, 100,000 expanded stockout days total. Scans require OCR and are rejected.
  Returns 201 with `dataset`, `source`, `warehouse_id`, `counts`,
  `warnings`, `preview`, `products`. No calculation or order is triggered.
  All validation must succeed before publication. Invalid input: 422;
  unsupported format: 415; size limit: 413.
- `GET /api/v1/datasets/{dataset}`: same metadata for a published upload; 404
  otherwise. Dataset-specific originals are not returned or sent to OpenAI.
- `GET /api/v1/datasets/template.xlsx`: six-sheet template with **synthetic**
  example data, extra transaction fields, warehouse and product metadata.
- `GET /api/v1/runs/{run_id}/export?format=csv|xlsx&sku=...`: export a persisted
  calculation (all SKUs or repeated `sku` parameters), grouped by supplier.
  Columns: SKU, product, supplier ID/name, recommended quantity, urgency, reasons.
  Unknown run or selected SKU: 404. Unsupported format: 422.
  This exports recommendations, never creates/posts a document in 1C.
- `GET /api/v1/items/{sku}?run_id=...`: optional exact run lookup; old behavior
  without run_id is retained for compatibility.

Import metadata schema: `contracts/import.response.schema.json`.
The import response contains normalized previews (up to 5 rows per table) without
customer identifiers. `products` contains sku, name, category and unit when supplied.
The returned dataset is accepted by the existing recalculate request.
Missing price/customer data is a visible quality warning, not invented.
Multiple warehouses require an explicit warehouse selection; silent merging is forbidden.
1C mapping and PDF limitations: [INPUT_OUTPUT.md](INPUT_OUTPUT.md).

## Change procedure

1. Update this file first.
2. Update the JSON Schema when the response changes.
3. Send one change notice to the backend and frontend owners.
4. Update implementation and mock data together.
5. Run schema validation and the smoke test before merge.
