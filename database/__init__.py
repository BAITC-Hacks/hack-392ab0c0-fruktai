"""Optional SQLite persistence for local inspection and audit."""

from .repository import (
    DatabaseError,
    RecordNotFoundError,
    database_stats,
    initialize_database,
    latest_agent_steps,
    latest_item_detail,
    latest_recommendations,
    load_csv_dataset,
    save_calculation,
    supplier_order_summary,
)

__all__ = [
    "DatabaseError",
    "RecordNotFoundError",
    "database_stats",
    "initialize_database",
    "latest_agent_steps",
    "latest_item_detail",
    "latest_recommendations",
    "load_csv_dataset",
    "save_calculation",
    "supplier_order_summary",
]
