# FruktAI — MVP specification

## 1. Goal

FruktAI automatically prepares explainable replenishment recommendations from prepared CSV files. The MVP reduces stockout risk and excess inventory without allowing an LLM to choose order quantities.

The core user flow is:

1. Load the `demo` dataset.
2. Validate input data.
3. Exclude one-off sales outliers.
4. Estimate demand lost during stockouts.
5. Forecast demand during supplier lead time.
6. Calculate a non-negative order recommendation.
7. Group and display recommendations by supplier.
8. Explain urgency and calculation factors.
9. Recalculate after an `on_hand` or `in_transit` override.

## 2. MVP boundaries

Included:

- prepared CSV input, with no required database;
- deterministic calculation and deterministic workflow;
- `GET /health`, `POST /api/v1/recalculate`, and `GET /api/v1/items/{sku}`;
- a dashboard driven only by the documented API response;
- item history with anomaly and stockout markers;
- per-step run journal;
- Docker Compose or documented local commands;
- one demo dataset and a repeatable demo scenario.

Not included:

- automatic ordering or supplier communication;
- authentication, payments, 1C integration, Redis, Celery, or WebSockets;
- probabilistic agent decisions;
- an LLM in the quantity calculation path;
- database persistence or production cloud infrastructure;
- optimization for minimum order quantity, package size, budget, or truck capacity.

## 3. Source data

The dataset consists of six CSV files described in [docs/DATA_CONTRACT.md](docs/DATA_CONTRACT.md):

- `sales.csv`;
- `inventory.csv`;
- `stockouts.csv`;
- `suppliers.csv`;
- `in_transit.csv`;
- `products.csv`.

`sku` and `supplier_id` are strings and must not be converted to numbers. Dates use ISO `YYYY-MM-DD`.

## 4. Deterministic calculation

For every active SKU:

```text
recommended_qty = max(
  0,
  forecast_demand_during_lead_time
  + safety_stock
  - on_hand
  - in_transit
)
```

The final quantity is rounded up to a whole unit.

MVP calculation policy:

1. Aggregate sales into daily units per SKU.
2. Mark a daily sale as an outlier when it is above `Q3 + 1.5 * IQR`; if IQR is zero, do not remove observations solely because of this rule.
3. Compute baseline average daily demand from non-outlier, in-stock observations in the most recent 28 calendar days available. If fewer than 7 valid days exist, use all valid history and add a warning reason.
4. Estimate stockout compensation as `baseline_daily_demand * stockout_days` inside the demand window. Stockout days do not reduce the denominator of the baseline.
5. Seasonality factor is the ratio of the latest 7 valid days to the 28-day baseline, clamped to `[0.75, 1.50]`. With fewer than 28 calendar days of history, use `1.0`.
6. Growth factor compares the latest 14 valid days with the preceding 14 valid days. Apply growth only when both windows have at least 7 valid days; clamp the factor to `[1.0, 1.30]` so a decline does not duplicate the seasonality adjustment.
7. Adjusted average daily demand is `(valid_units + stockout_compensation) / calendar_days_in_window`.
8. Forecast demand is `adjusted_average_daily_demand * lead_time_days * seasonality_factor * growth_factor`.
9. Safety stock is `adjusted_average_daily_demand * safety_stock_days`. `safety_stock_days` defaults to 7 in the backend configuration.

Values returned through the API are rounded to two decimal places, except `recommended_qty`, which is rounded up to an integer.

## 5. Urgency

Urgency is deterministic:

- `high`: projected available units (`on_hand + in_transit`) are less than forecast lead-time demand, or current `on_hand` is zero;
- `medium`: projected available units are below forecast demand plus safety stock;
- `low`: no shortage is projected.

The response contains explicit `reasons`; they are generated from calculation facts and never alter the result.

## 6. Controlled fallbacks and validation

- With insufficient seasonal history, `seasonality_factor = 1.0` and a reason is recorded.
- A missing SKU in `in_transit.csv` means `in_transit = 0` and a warning reason is recorded.
- Negative `on_hand`, `in_transit`, sales units, lead time, or stockout duration is a data error.
- Unknown override SKUs and duplicate master-data keys are errors.
- `recommended_qty` must be zero or positive.
- Non-finite numeric results (`NaN`, positive or negative infinity) fail result validation.
- A failed workflow step stops the run; its failure is written to the journal and no successful recommendation response is fabricated.

## 7. Workflow

The deterministic orchestrator records start time, finish time, status, and message for each step:

1. `load_data`
2. `validate_data`
3. `detect_outliers`
4. `estimate_lost_demand`
5. `calculate_recommendations`
6. `validate_result`
7. `save_result`

The backend may call the orchestrator as a Python function. The smoke test calls the backend API. The fixed wire contract is [docs/API_CONTRACT.md](docs/API_CONTRACT.md).

## 8. Acceptance criteria

- All three endpoints match the API contract.
- The same dataset and overrides produce the same quantities.
- Every recommendation can be reconstructed from returned inputs and factors.
- Increasing `on_hand` for an orderable SKU lowers or preserves `recommended_qty`; the demo SKU used by the smoke test must lower it.
- Recommendations are groupable by `supplier_id` without client-side invented fields.
- The workflow journal contains all completed steps in execution order.
- The project starts using the README instructions and passes the smoke test.

