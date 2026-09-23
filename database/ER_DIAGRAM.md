# FruktAI database structure

This is an optional SQLite projection for inspecting CSV source data, calculation runs, recommendations, and workflow logs. CSV remains the MVP source of truth.

```mermaid
erDiagram
    SUPPLIERS ||--o{ PRODUCTS : supplies
    PRODUCTS ||--o{ SALES : has
    PRODUCTS ||--o| INVENTORY : has
    PRODUCTS ||--o{ IN_TRANSIT : receives
    PRODUCTS ||--o{ STOCKOUTS : experiences
    CALCULATION_RUNS ||--o{ RUN_OVERRIDES : receives
    PRODUCTS ||--o{ RUN_OVERRIDES : overrides
    CALCULATION_RUNS ||--o{ RECOMMENDATIONS : produces
    PRODUCTS ||--o{ RECOMMENDATIONS : calculated_for
    SUPPLIERS ||--o{ RECOMMENDATIONS : grouped_by
    CALCULATION_RUNS ||--o{ AGENT_STEPS : logs
    CALCULATION_RUNS ||--o{ ITEM_HISTORY : derives
    PRODUCTS ||--o{ ITEM_HISTORY : charts

    SUPPLIERS {
        text supplier_id PK
        text supplier_name
        integer lead_time_days
    }
    PRODUCTS {
        text sku PK
        text name
        text supplier_id FK
        integer active
    }
    SALES {
        integer sale_id PK
        text sale_date
        text sku FK
        real units
    }
    INVENTORY {
        text sku PK,FK
        integer on_hand
        text updated_at
    }
    IN_TRANSIT {
        integer shipment_id PK
        text sku FK
        integer quantity
        text expected_date
    }
    STOCKOUTS {
        integer stockout_id PK
        text sku FK
        text start_date
        text end_date
    }
    CALCULATION_RUNS {
        text run_id PK
        text dataset
        text generated_at
        text status
    }
    RUN_OVERRIDES {
        text run_id PK,FK
        text sku PK,FK
        integer on_hand
        integer in_transit
    }
    RECOMMENDATIONS {
        text run_id PK,FK
        text sku PK,FK
        integer recommended_qty
        text urgency
        real forecast_demand
        real safety_stock
    }
    AGENT_STEPS {
        text run_id PK,FK
        integer step_order PK
        text step
        text status
    }
    ITEM_HISTORY {
        text run_id PK,FK
        text sku PK,FK
        text history_date PK
        real units
        integer is_outlier
        integer is_stockout
    }
```

## Viewing in Visual Studio Code

1. Open `database/schema.sql` to inspect all tables and constraints.
2. Install any trusted SQLite viewer extension only if you want a graphical table browser.
3. Create an empty local database using the extension's **Run Query** action against `schema.sql`.
4. Inspect the `latest_recommendations` and `supplier_order_summary` views after data is loaded.

The repository intentionally stores only the SQL definition, not a generated binary `.db` file or fake calculation rows.

