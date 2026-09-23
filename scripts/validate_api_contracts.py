"""Dependency-free validation for FruktAI API JSON Schemas.

The validator implements the JSON Schema keywords used by this repository. It
checks schema references, contract examples, expected rejection cases, and a
real response produced by the deterministic workflow.
"""

from __future__ import annotations

import copy
import json
import math
import re
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from agent import run_workflow_with_details  # noqa: E402
from scripts.test_agent_workflow import build_dataset  # noqa: E402


class SchemaValidationError(AssertionError):
    pass


def resolve_reference(root: dict[str, Any], reference: str) -> dict[str, Any]:
    if not reference.startswith("#/"):
        raise SchemaValidationError(f"Only local references are supported: {reference}")
    current: Any = root
    for raw_part in reference[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or part not in current:
            raise SchemaValidationError(f"Unresolved schema reference: {reference}")
        current = current[part]
    if not isinstance(current, dict):
        raise SchemaValidationError(f"Schema reference is not an object: {reference}")
    return current


def check_references(value: Any, root: dict[str, Any]) -> None:
    if isinstance(value, dict):
        reference = value.get("$ref")
        if reference is not None:
            resolve_reference(root, reference)
        for child in value.values():
            check_references(child, root)
    elif isinstance(value, list):
        for child in value:
            check_references(child, root)


def validate(instance: Any, schema: dict[str, Any], root: dict[str, Any], path: str = "$") -> None:
    if "$ref" in schema:
        validate(instance, resolve_reference(root, schema["$ref"]), root, path)
        return

    if "oneOf" in schema:
        matches = sum(
            _matches(instance, option, root, path) for option in schema["oneOf"]
        )
        if matches != 1:
            raise SchemaValidationError(f"{path}: expected exactly one oneOf match, got {matches}")

    if "anyOf" in schema and not any(
        _matches(instance, option, root, path) for option in schema["anyOf"]
    ):
        raise SchemaValidationError(f"{path}: no anyOf option matched")

    if "const" in schema and instance != schema["const"]:
        raise SchemaValidationError(f"{path}: expected constant {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        raise SchemaValidationError(f"{path}: {instance!r} is not in {schema['enum']!r}")

    expected_type = schema.get("type")
    if expected_type and not _has_type(instance, expected_type):
        raise SchemaValidationError(f"{path}: expected {expected_type}, got {type(instance).__name__}")

    if isinstance(instance, dict):
        required = schema.get("required", [])
        missing = [field for field in required if field not in instance]
        if missing:
            raise SchemaValidationError(f"{path}: missing fields {missing}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = set(instance) - set(properties)
            if extra:
                raise SchemaValidationError(f"{path}: unexpected fields {sorted(extra)}")
        for key, child in instance.items():
            if key in properties:
                validate(child, properties[key], root, f"{path}.{key}")

    if isinstance(instance, list) and "items" in schema:
        for index, child in enumerate(instance):
            validate(child, schema["items"], root, f"{path}[{index}]")

    if isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0):
            raise SchemaValidationError(f"{path}: string is shorter than minLength")
        pattern = schema.get("pattern")
        if pattern and re.search(pattern, instance) is None:
            raise SchemaValidationError(f"{path}: string does not match {pattern!r}")
        _validate_format(instance, schema.get("format"), path)

    if (
        isinstance(instance, (int, float))
        and not isinstance(instance, bool)
        and "minimum" in schema
        and instance < schema["minimum"]
    ):
        raise SchemaValidationError(f"{path}: value is below minimum {schema['minimum']}")
    if isinstance(instance, float) and not math.isfinite(instance):
        raise SchemaValidationError(f"{path}: non-finite JSON number")


def _matches(instance: Any, schema: dict[str, Any], root: dict[str, Any], path: str) -> bool:
    try:
        validate(instance, schema, root, path)
    except SchemaValidationError:
        return False
    return True


def _has_type(instance: Any, expected: str) -> bool:
    mapping = {
        "object": lambda value: isinstance(value, dict),
        "array": lambda value: isinstance(value, list),
        "string": lambda value: isinstance(value, str),
        "boolean": lambda value: isinstance(value, bool),
        "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
        "number": lambda value: isinstance(value, (int, float))
        and not isinstance(value, bool)
        and not (isinstance(value, float) and not math.isfinite(value)),
    }
    if expected not in mapping:
        raise SchemaValidationError(f"Unsupported schema type: {expected}")
    return mapping[expected](instance)


def _validate_format(value: str, expected: str | None, path: str) -> None:
    try:
        if expected == "date":
            date.fromisoformat(value)
        elif expected == "date-time":
            datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SchemaValidationError(f"{path}: invalid {expected}") from error


def expect_invalid(instance: Any, schema: dict[str, Any], label: str) -> None:
    try:
        validate(instance, schema, schema)
    except SchemaValidationError:
        return
    raise AssertionError(f"{label} unexpectedly passed validation")


def load_schemas() -> dict[str, dict[str, Any]]:
    contract_dir = REPOSITORY_ROOT / "contracts"
    schemas: dict[str, dict[str, Any]] = {}
    identifiers: set[str] = set()
    for path in sorted(contract_dir.glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise AssertionError(f"{path.name}: unexpected JSON Schema draft")
        identifier = schema.get("$id")
        if not identifier or identifier in identifiers:
            raise AssertionError(f"{path.name}: missing or duplicate $id")
        identifiers.add(identifier)
        check_references(schema, schema)
        schemas[path.name] = schema
    expected = {
        "ai-explanation.input.schema.json",
        "ai-explanation.output.schema.json",
        "health.response.schema.json",
        "recalculate.request.schema.json",
        "recommendation.schema.json",
        "item.response.schema.json",
        "error.response.schema.json",
    }
    if set(schemas) != expected:
        raise AssertionError(f"schema manifest mismatch: {set(schemas) ^ expected}")
    return schemas


def main() -> int:
    schemas = load_schemas()

    health_schema = schemas["health.response.schema.json"]
    validate({"status": "ok"}, health_schema, health_schema)
    expect_invalid({"status": "healthy"}, health_schema, "invalid health status")

    request_schema = schemas["recalculate.request.schema.json"]
    valid_request = {
        "dataset": "demo",
        "overrides": [{"sku": "SKU-001", "on_hand": 25, "in_transit": 20}],
    }
    validate(valid_request, request_schema, request_schema)
    expect_invalid(
        {"dataset": "../demo", "overrides": []},
        request_schema,
        "unsafe dataset path",
    )
    expect_invalid(
        {"dataset": "demo", "overrides": [{"sku": "SKU-001"}]},
        request_schema,
        "override without a value",
    )

    error_schema = schemas["error.response.schema.json"]
    validate({"detail": "Dataset not found"}, error_schema, error_schema)
    validate(
        {
            "detail": [
                {
                    "loc": ["body", "overrides", 0, "on_hand"],
                    "msg": "Input should be greater than or equal to 0",
                    "type": "greater_than_equal",
                }
            ]
        },
        error_schema,
        error_schema,
    )

    item_schema = schemas["item.response.schema.json"]
    item_response = {
        "sku": "SKU-001",
        "name": "Contract test item",
        "history": [
            {
                "date": "2026-09-01",
                "units": 10.0,
                "is_outlier": False,
                "is_stockout": False,
                "estimated_lost_units": 0.0,
            }
        ],
        "calculation": {
            "recommended_qty": 20,
            "on_hand": 10,
            "in_transit": 5,
            "lead_time_days": 7,
            "avg_daily_demand": 5.0,
            "forecast_demand": 35.0,
            "safety_stock": 35.0,
            "seasonality_factor": 1.0,
            "growth_factor": 1.0,
            "stockout_compensation": 0.0,
            "outlier_units_removed": 0.0,
            "days_of_cover": 3.0,
            "reasons": ["Contract validation fixture"],
        },
    }
    validate(item_response, item_schema, item_schema)

    ai_input_schema = schemas["ai-explanation.input.schema.json"]
    ai_input = {
        "recommendations": [
            {
                "sku": "SKU-001",
                "name": "Contract test item",
                "supplier_id": "SUP-001",
                "supplier_name": "Contract test supplier",
                "recommended_qty": 20,
                "urgency": "high",
                "on_hand": 10,
                "in_transit": 5,
                "lead_time_days": 7,
                "avg_daily_demand": 5.0,
                "forecast_demand": 35.0,
                "safety_stock": 35.0,
                "seasonality_factor": 1.0,
                "growth_factor": 1.0,
                "stockout_compensation": 0.0,
                "outlier_units_removed": 0.0,
                "days_of_cover": 3.0,
                "deterministic_reasons": ["Contract validation fixture"],
            }
        ]
    }
    validate(ai_input, ai_input_schema, ai_input_schema)
    ai_output_schema = schemas["ai-explanation.output.schema.json"]
    validate(
        {
            "explanations": [
                {
                    "sku": "SKU-001",
                    "explanation": "Краткое проверяемое объяснение.",
                }
            ]
        },
        ai_output_schema,
        ai_output_schema,
    )
    expect_invalid(
        {
            "explanations": [
                {
                    "sku": "SKU-001",
                    "explanation": "Краткое объяснение.",
                    "recommended_qty": 999,
                }
            ]
        },
        ai_output_schema,
        "AI output attempting to set quantity",
    )

    recommendation_schema = schemas["recommendation.schema.json"]
    with tempfile.TemporaryDirectory(prefix="fruktai-contract-") as temp:
        root = Path(temp)
        dataset = root / "demo"
        dataset.mkdir()
        build_dataset(dataset)
        execution = run_workflow_with_details(dataset, output_dir=root / "runs")
        response = execution.response
        validate(response, recommendation_schema, recommendation_schema)
        validate(
            execution.item_details["SKU-001"],
            item_schema,
            item_schema,
        )
        invalid_response = copy.deepcopy(response)
        invalid_response["recommendations"][0]["recommended_qty"] = -1
        expect_invalid(
            invalid_response,
            recommendation_schema,
            "negative recommendation",
        )

    print(f"API contracts: OK ({len(schemas)} schemas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
