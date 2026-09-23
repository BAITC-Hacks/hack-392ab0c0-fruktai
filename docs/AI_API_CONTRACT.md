# FruktAI AI API contract

Version: `1.0.0`

Provider: OpenAI Responses API
Scope: explanation only, after the deterministic calculation

This contract defines the complete AI stage used by `WorkflowService`. It does
not add or rename fields in the public FruktAI HTTP API.

## Goal and safety boundary

The AI stage turns already validated calculation facts into concise Russian
explanations for a purchasing manager. It must never calculate, replace, or
correct `recommended_qty` or any other business value.

The order quantity remains:

```text
max(0, forecast_demand + safety_stock - on_hand - in_transit)
```

The model is called only after the deterministic workflow has loaded and
validated data, removed outliers, estimated lost demand, calculated the result,
and validated the formula.

## End-to-end funnel

```text
POST /api/v1/recalculate
  -> deterministic seven-step workflow
  -> validated recommendation response
  -> select up to OPENAI_MAX_EXPLANATION_ITEMS
  -> build anonymized aggregate AI input
  -> one batched POST /v1/responses
  -> strict JSON Schema output
  -> exact SKU/cardinality/content validation
  -> protected-field immutability check
  -> append text to reasons
  -> persist the same enriched response and item details
```

The batch is atomic. If one expected SKU is missing, duplicated, unknown, too
long, refused, or malformed, no AI text from that batch is merged.

## AI input

Machine-readable contract:
[`contracts/ai-explanation.input.schema.json`](../contracts/ai-explanation.input.schema.json).

Each selected recommendation sends only these aggregate fields:

- identity: `sku`, `name`, `supplier_id`, `supplier_name`;
- fixed decision: `recommended_qty`, `urgency`;
- supply facts: `on_hand`, `in_transit`, `lead_time_days`;
- demand facts: `avg_daily_demand`, `forecast_demand`, `safety_stock`;
- must-have signals: `seasonality_factor`, `growth_factor`,
  `stockout_compensation`, `outlier_units_removed`;
- coverage and traceability: `days_of_cover`, `deterministic_reasons`.

Example:

```json
{
  "recommendations": [
    {
      "sku": "SKU-001",
      "name": "Кабель ВВГ",
      "supplier_id": "SUP-01",
      "supplier_name": "Поставщик 1",
      "recommended_qty": 48,
      "urgency": "high",
      "on_hand": 25,
      "in_transit": 20,
      "lead_time_days": 7,
      "avg_daily_demand": 8.0,
      "forecast_demand": 56.0,
      "safety_stock": 56.0,
      "seasonality_factor": 1.0,
      "growth_factor": 1.0,
      "stockout_compensation": 0.0,
      "outlier_units_removed": 120.0,
      "days_of_cover": 5.63,
      "deterministic_reasons": ["One-off sales outlier excluded"]
    }
  ]
}
```

Raw sales, prices, warehouses, customer identifiers, CSV files, database rows,
API keys, and user overrides are not sent to OpenAI. Client data must already be
anonymized before it enters FruktAI; the AI boundary removes client-level data
entirely.

## OpenAI request

The application sends one `POST https://api.openai.com/v1/responses` request per
calculation run, with:

- the configured `model`;
- fixed purchasing-explanation instructions;
- the JSON input above;
- `text.format.type = json_schema`, `strict = true`;
- the output schema below;
- `store = false`;
- a bounded output-token limit.

The API key is supplied only in the server-side `Authorization` header.

## AI output

Machine-readable contract:
[`contracts/ai-explanation.output.schema.json`](../contracts/ai-explanation.output.schema.json).

```json
{
  "explanations": [
    {
      "sku": "SKU-001",
      "explanation": "Заказ покрывает прогноз на срок поставки и страховой запас с учётом остатка и товара в пути."
    }
  ]
}
```

The output deliberately has no quantity, urgency, forecast, supplier, or
summary field. Application validation additionally requires exactly one item
for every requested SKU, no unknown or duplicate SKU, non-empty plain text, and
at most 500 characters per explanation.

After validation, the text becomes one additional public API reason:

```json
"reasons": ["AI-пояснение: Заказ покрывает прогноз ..."]
```

All other public response fields remain byte-for-byte equivalent as Python
values to the deterministic result.

## Must-have coverage

| Case requirement | Deterministic source of truth | AI use |
|---|---|---|
| All source data affects replenishment | Orchestrator calculation and validation | Explains the resulting aggregate facts only |
| Seasonality and sustainable growth | `seasonality_factor`, `growth_factor`, `forecast_demand` | Mentions a factor only when material |
| Lost demand during stockout | `stockout_compensation` | Explains upward correction when positive |
| One-off large orders excluded | `outlier_units_removed`, deterministic reason | Explains that the spike was excluded |
| Supplier grouping and reason per item | `supplier_id`, `supplier_name`, public `reasons` | Adds one readable reason per selected SKU |

The AI stage cannot make a missing deterministic must-have pass. Its role is
explanation, not calculation or data repair.

## Failure and retry policy

- HTTP `408`, `409`, `429`, `5xx`, timeouts, and network failures are retried
  with bounded exponential backoff.
- Authentication, permission, model-not-found, and malformed-output errors are
  not retried unless the HTTP status is transient.
- After retry exhaustion the deterministic response is returned unchanged.
- No partial AI batch is saved.
- Logs contain model, item count, attempt count, and a safe error class/message;
  they never contain the API key or raw provider response body.

The internal `AIEnrichmentReport` records `completed`, `skipped`, or `fallback`,
requested/enriched item counts, attempts, model, and a safe message. It is not a
new public API field.

## Acceptance checks

The offline test must prove:

1. one batch request serves all selected items;
2. input contains every must-have aggregate signal and no client identifier;
3. strict structured output is requested;
4. every protected numeric/business field is unchanged;
5. incomplete output triggers all-or-nothing fallback;
6. transient failures retry within the configured bound;
7. enriched reasons persist and are available through item details.

Run:

```bash
python scripts/validate_api_contracts.py
python scripts/test_openai_explainer.py
```
