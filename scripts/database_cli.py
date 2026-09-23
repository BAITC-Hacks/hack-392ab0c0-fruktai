"""Manage the optional FruktAI SQLite database.

Examples:

    python scripts/database_cli.py init
    python scripts/database_cli.py load --dataset-path data/demo
    python scripts/database_cli.py calculate --dataset-path data/demo
    python scripts/database_cli.py show recommendations
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from agent import run_workflow_with_details  # noqa: E402
from database import (  # noqa: E402
    DatabaseError,
    database_stats,
    initialize_database,
    latest_agent_steps,
    latest_recommendations,
    load_csv_dataset,
    save_calculation,
    supplier_order_summary,
)


DEFAULT_DATABASE = REPOSITORY_ROOT / "artifacts" / "fruktai.sqlite"
DEFAULT_RUNS = REPOSITORY_ROOT / "artifacts" / "runs"


def print_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("No rows")
        return
    columns = list(rows[0])
    widths = {
        column: max(
            len(column),
            *(len(_display(row.get(column))) for row in rows),
        )
        for column in columns
    }
    print(" | ".join(column.ljust(widths[column]) for column in columns))
    print("-+-".join("-" * widths[column] for column in columns))
    for row in rows:
        print(" | ".join(_display(row.get(column)).ljust(widths[column]) for column in columns))


def _display(value: Any) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= 80 else f"{text[:77]}..."


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FruktAI SQLite utility")
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DATABASE,
        help=f"SQLite file (default: {DEFAULT_DATABASE})",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("init", help="Create tables and views")

    load = commands.add_parser("load", help="Load and validate six source CSV files")
    load.add_argument("--dataset-path", type=Path, default=Path("data/demo"))

    calculate = commands.add_parser(
        "calculate", help="Sync CSV, run the workflow, and persist its result"
    )
    calculate.add_argument("--dataset-path", type=Path, default=Path("data/demo"))
    calculate.add_argument("--dataset-name", default=None)
    calculate.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS)

    show = commands.add_parser("show", help="Print database content")
    show.add_argument(
        "target",
        choices=("recommendations", "suppliers", "steps", "tables"),
    )
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    try:
        if arguments.command == "init":
            path = initialize_database(arguments.db)
            print(f"Database initialized: {path.resolve()}")
        elif arguments.command == "load":
            counts = load_csv_dataset(arguments.db, arguments.dataset_path)
            print(f"Dataset loaded into: {arguments.db.resolve()}")
            print_table([{"table": name, "rows": count} for name, count in counts.items()])
        elif arguments.command == "calculate":
            counts = load_csv_dataset(arguments.db, arguments.dataset_path)
            execution = run_workflow_with_details(
                arguments.dataset_path,
                output_dir=arguments.runs_dir,
            )
            dataset_name = arguments.dataset_name or arguments.dataset_path.name
            run_id = save_calculation(
                arguments.db,
                dataset_name,
                execution.response,
                item_details=execution.item_details,
            )
            print(
                f"Saved run {run_id} with {counts['products']} products to {arguments.db.resolve()}"
            )
        elif arguments.command == "show":
            readers = {
                "recommendations": latest_recommendations,
                "suppliers": supplier_order_summary,
                "steps": latest_agent_steps,
                "tables": database_stats,
            }
            print_table(readers[arguments.target](arguments.db))
    except (DatabaseError, FileNotFoundError, ValueError) as error:
        print(f"database command failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
