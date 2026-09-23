import pandas as pd

from backend.calculation import calculate_recommendations
from database import initialize_database, latest_item, latest_recommendations, latest_summary, persist_run, set_approval


def test_recommendations_survive_database_reopen(tmp_path):
    sales = pd.DataFrame([
        {"date": "2026-01-01", "sku": "db-1", "quantity": 4, "customer_id": "anon-1", "stockout": False},
        {"date": "2026-01-02", "sku": "db-1", "quantity": 5, "customer_id": "anon-2", "stockout": False},
    ])
    inventory = pd.DataFrame([{
        "sku": "DB-1", "supplier": "Supplier DB", "on_hand": 1,
        "in_transit": 0, "lead_time_days": 3, "name": "Database item",
    }])
    response = calculate_recommendations(sales, inventory).model_dump()
    database_file = tmp_path / "integration.sqlite"

    run_id = persist_run(sales, inventory, response, path=database_file)

    assert run_id
    initialize_database(database_file)
    stored = latest_item("db-1", database_file)
    assert stored["sku"] == "DB-1"
    assert stored["recommended_qty"] == response["recommendations"][0]["recommended_qty"]
    assert latest_recommendations(database_file)[0]["sku"] == "DB-1"
    assert latest_summary(database_file)["sku_count"] == 1
    set_approval(True, "human confirmed", database_file)
    assert latest_summary(database_file)["approved"] is True
