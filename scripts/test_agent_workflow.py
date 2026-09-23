"""Dependency-free regression test for the deterministic workflow.

Run from the repository root:

    python scripts/test_agent_workflow.py
"""

from __future__ import annotations

import csv
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from agent import DataValidationError, run_workflow  # noqa: E402


def write_csv(path: Path, headers: list[str], rows: list[list[object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(headers)
        writer.writerows(rows)


def build_dataset(path: Path) -> None:
    write_csv(
        path / "products.csv",
        ["sku", "name", "supplier_id", "active"],
        [["SKU-001", "Test apples", "SUP-01", "true"]],
    )
    write_csv(
        path / "suppliers.csv",
        ["supplier_id", "supplier_name", "lead_time_days"],
        [["SUP-01", "Test supplier", 7]],
    )
    write_csv(path / "inventory.csv", ["sku", "on_hand"], [["SKU-001", 10]])
    write_csv(
        path / "in_transit.csv",
        ["sku", "quantity", "expected_date"],
        [["SKU-001", 5, "2026-09-30"]],
    )
    write_csv(
        path / "stockouts.csv",
        ["sku", "start_date", "end_date"],
        [["SKU-001", "2026-09-10", "2026-09-11"]],
    )
    start = date(2026, 8, 27)
    rows: list[list[object]] = []
    for offset in range(28):
        day = start + timedelta(days=offset)
        units = 100 if offset == 8 else 10 + (offset // 14)
        rows.append([day.isoformat(), "SKU-001", units])
    write_csv(path / "sales.csv", ["date", "sku", "units"], rows)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="fruktai-agent-") as temp:
        root = Path(temp)
        dataset = root / "demo"
        output = root / "runs"
        dataset.mkdir()
        build_dataset(dataset)

        baseline = run_workflow(dataset, output_dir=output)
        changed = run_workflow(
            dataset,
            overrides=[{"sku": "SKU-001", "on_hand": 40}],
            output_dir=output,
        )

        required = {"run_id", "generated_at", "summary", "recommendations", "agent_steps"}
        assert required <= baseline.keys()
        assert [entry["step"] for entry in baseline["agent_steps"]] == [
            "load_data",
            "validate_data",
            "detect_outliers",
            "estimate_lost_demand",
            "calculate_recommendations",
            "validate_result",
            "save_result",
        ]
        first = baseline["recommendations"][0]
        updated = changed["recommendations"][0]
        assert first["recommended_qty"] >= 0
        assert updated["recommended_qty"] < first["recommended_qty"]
        assert baseline["summary"]["anomalies_removed"] == 1
        assert baseline["summary"]["estimated_stockout_items"] == 1
        assert (output / f"{baseline['run_id']}.json").is_file()

        fallback_dataset = root / "fallback"
        fallback_dataset.mkdir()
        build_dataset(fallback_dataset)
        write_csv(
            fallback_dataset / "in_transit.csv",
            ["sku", "quantity", "expected_date"],
            [],
        )
        short_sales = [
            [f"2026-09-{day:02d}", "SKU-001", 10] for day in range(1, 7)
        ]
        write_csv(
            fallback_dataset / "sales.csv",
            ["date", "sku", "units"],
            short_sales,
        )
        fallback = run_workflow(fallback_dataset, output_dir=output)
        fallback_item = fallback["recommendations"][0]
        assert fallback_item["in_transit"] == 0
        assert fallback_item["seasonality_factor"] == 1.0
        assert any("fallback uses 0" in reason for reason in fallback_item["reasons"])
        assert any(
            "Insufficient seasonal history" in reason
            for reason in fallback_item["reasons"]
        )

        try:
            run_workflow(
                dataset,
                overrides=[{"sku": "SKU-001", "on_hand": -1}],
                output_dir=output,
            )
        except DataValidationError:
            pass
        else:
            raise AssertionError("negative inventory must fail validation")

    print("agent workflow test: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
