# OpenAI integration runbook

The full AI data contract and must-have mapping are defined in
[AI_API_CONTRACT.md](AI_API_CONTRACT.md). OpenAI is an optional explanation
stage after the validated deterministic calculation. It never determines order
quantity.

## Configuration

Keep the secret only in a local `.env` or backend environment:

```env
OPENAI_API_KEY=sk-your-real-key
OPENAI_MODEL=gpt-6-astra
OPENAI_EXPLANATIONS_ENABLED=true
OPENAI_TIMEOUT_SECONDS=20
OPENAI_MAX_EXPLANATION_ITEMS=20
OPENAI_MAX_RETRIES=2
OPENAI_RETRY_BASE_SECONDS=0.5
```

`.env` is ignored by Git. Never place the real key in `.env.example`, frontend
variables, source code, Docker images, logs, screenshots, or CI output.

`gpt-6-astra` is the configured quality-first model and was verified against the
current project key. If the API project cannot access it, set `OPENAI_MODEL` to
an available text model. Model availability and limits are account-dependent.

## Backend integration point

The backend creates one long-lived service instance:

```python
from agent import WorkflowService

service = WorkflowService.from_environment()
```

`WorkflowService.recalculate()` runs the deterministic workflow, sends all
selected recommendation facts in one OpenAI request, validates the structured
response, appends the explanations, and persists the final data.

When `OPENAI_EXPLANATIONS_ENABLED=false`, no key is required and no OpenAI
request is made. When it is `true`, a missing key fails service configuration at
startup instead of silently pretending AI is enabled.

## Runtime behavior

- One batched Responses API call is made per calculation run, not one per SKU.
- `OPENAI_MAX_EXPLANATION_ITEMS` caps items sent in that batch.
- `store=false` is sent to the provider.
- Strict Structured Outputs allows only `sku` and `explanation`.
- Each explanation is normalized to one line and limited to 500 characters.
- Exact SKU membership and cardinality are checked before merge.
- The whole batch is discarded on any validation or API failure.
- Deterministic reasons remain available in every fallback path.

The public HTTP contract is unchanged. AI text is appended to the existing
`reasons` array as `AI-пояснение: ...`.

## Retry and fallback

The client retries only temporary failures (`408`, `409`, `429`, `5xx`, network
failure, timeout). Attempts are bounded by `OPENAI_MAX_RETRIES`; delay starts at
`OPENAI_RETRY_BASE_SECONDS`, doubles per retry, and is capped at eight seconds.
`Retry-After` is respected when it contains seconds.

After retry exhaustion, refusal, invalid JSON, schema mismatch, missing SKU, or
unknown SKU, the service returns and persists the original deterministic result
without partial AI text. The error log never includes the key or raw response
body.

## Checks

Offline checks do not use an API key or budget:

```bash
python scripts/validate_api_contracts.py
python scripts/test_openai_explainer.py
python scripts/test_workflow_service.py
```

The explicit live check performs one item request and never prints the key:

```bash
python scripts/check_openai_connection.py --env-file .env
```

Expected result:

```text
OpenAI connection: OK (model=gpt-6-astra)
Explanation: ...
```

If it fails, first check the model ID, project access, quota, and outbound HTTPS
access. The deterministic MVP remains operational while AI explanations fall
back.
