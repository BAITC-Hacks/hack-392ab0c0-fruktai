"""Make one explicit OpenAI Responses API connection check.

The script loads only known OpenAI variables from an optional local `.env` and
never prints the API key.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from agent import OpenAIAPIError, OpenAIExplainer  # noqa: E402


ALLOWED_ENV = {
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "OPENAI_TIMEOUT_SECONDS",
    "OPENAI_MAX_EXPLANATION_ITEMS",
    "OPENAI_MAX_RETRIES",
    "OPENAI_RETRY_BASE_SECONDS",
}


def load_allowed_env(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Environment file not found: {path}")
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name in ALLOWED_ENV and name not in os.environ:
            os.environ[name] = value.strip().strip('"').strip("'")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--model", default=None)
    arguments = parser.parse_args()
    try:
        load_allowed_env(arguments.env_file)
        if arguments.model:
            os.environ["OPENAI_MODEL"] = arguments.model
        explainer = OpenAIExplainer.from_environment()
        text = explainer.explain(
            {
                "sku": "CHECK-001",
                "name": "Проверка подключения",
                "supplier_id": "CHECK-SUPPLIER",
                "supplier_name": "Тестовый поставщик",
                "recommended_qty": 10,
                "urgency": "medium",
                "on_hand": 5,
                "in_transit": 0,
                "lead_time_days": 7,
                "avg_daily_demand": 1.0,
                "forecast_demand": 7.0,
                "safety_stock": 7.0,
                "seasonality_factor": 1.0,
                "growth_factor": 1.0,
                "stockout_compensation": 0.0,
                "outlier_units_removed": 0.0,
                "days_of_cover": 5.0,
                "reasons": ["Connection check with deterministic facts"],
            }
        )
    except (FileNotFoundError, OpenAIAPIError, ValueError) as error:
        print(f"OpenAI connection: FAILED: {error}", file=sys.stderr)
        return 1
    print(f"OpenAI connection: OK (model={explainer.model})")
    print(f"Explanation: {text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
