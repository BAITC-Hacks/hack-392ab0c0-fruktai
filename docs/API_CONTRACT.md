# FruktAI API contract

Contract version: `1.0.0`  
Base path: `/api/v1`  
Content type: `application/json`

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
| `dataset` | string | yes | Non-empty dataset directory name; MVP supports `demo`. |
| `overrides` | array | no | Defaults to `[]`; at most one entry per SKU. |
| `overrides[].sku` | string | yes | Must exist in `products.csv`. |
| `overrides[].on_hand` | integer | no | `>= 0`; omitted value uses CSV data. |
| `overrides[].in_transit` | integer | no | `>= 0`; omitted value uses CSV data. |

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

## Change process

1. Update this file first.
2. Update the JSON Schema when the response changes.
3. Send one change notice to the backend and frontend owners.
4. Update implementation and mock data together.
5. Run schema validation and the smoke test before merge.

