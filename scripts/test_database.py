"""Dependency-free integration test for SQLite import and run persistence."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from agent import run_workflow  # noqa: E402
from database import (  # noqa: E402
    database_stats,
    initialize_database,
    latest_agent_steps,
    latest_recommendations,
    load_csv_dataset,
    save_calculation,
    supplier_order_summary,
)
from scripts.test_agent_workflow import build_dataset  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="fruktai-database-") as temp:
        root = Path(temp)
        dataset = root / "demo"
        runs = root / "runs"
        database = root / "fruktai.sqlite"
        dataset.mkdir()
        build_dataset(dataset)

        initialize_database(database)
        counts = load_csv_dataset(database, dataset)
        assert counts == {
            "suppliers": 1,
            "products": 1,
            "inventory": 1,
            "sales": 28,
            "in_transit": 1,
            "stockouts": 1,
        }

        # The import is a source sync, so repeating it must not duplicate events.
        load_csv_dataset(database, dataset)
        stats = {row["table"]: row["rows"] for row in database_stats(database)}
        assert stats["sales"] == 28
        assert stats["in_transit"] == 1
        assert stats["stockouts"] == 1

        baseline = run_workflow(dataset, output_dir=runs)
        save_calculation(database, "demo", baseline)
        first = latest_recommendations(database)
        assert len(first) == 1
        assert first[0]["sku"] == "SKU-001"
        assert first[0]["recommended_qty"] > 0
        assert len(latest_agent_steps(database)) == 7
        supplier = supplier_order_summary(database)
        assert supplier[0]["total_units_to_order"] == first[0]["recommended_qty"]

        override = {
            "sku": "SKU-001",
            "on_hand": first[0]["on_hand"] + first[0]["recommended_qty"] + 1,
        }
        changed = run_workflow(dataset, overrides=[override], output_dir=runs)
        save_calculation(database, "demo", changed, overrides=[override])
        latest = latest_recommendations(database)
        assert latest[0]["recommended_qty"] < first[0]["recommended_qty"]
        assert stats.get("item_history", 0) == 0

        with closing(sqlite3.connect(database)) as connection:
            assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert connection.execute("PRAGMA foreign_key_check").fetchall() == []

    print("database integration test: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
