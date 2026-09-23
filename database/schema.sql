-- FruktAI optional SQLite schema for inspection and audit.
-- CSV files remain the required MVP input; this schema does not change the API.
-- Open this file directly in Visual Studio / VS Code or execute it with SQLite.

PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id       TEXT PRIMARY KEY,
    supplier_name     TEXT NOT NULL CHECK (length(trim(supplier_name)) > 0),
    lead_time_days    INTEGER NOT NULL CHECK (lead_time_days >= 0)
);

CREATE TABLE IF NOT EXISTS products (
    sku               TEXT PRIMARY KEY,
    name              TEXT NOT NULL CHECK (length(trim(name)) > 0),
    supplier_id       TEXT NOT NULL,
    active            INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    FOREIGN KEY (supplier_id) REFERENCES suppliers (supplier_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS sales (
    sale_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_date         TEXT NOT NULL CHECK (sale_date = date(sale_date)),
    sku               TEXT NOT NULL,
    units             REAL NOT NULL CHECK (units >= 0),
    FOREIGN KEY (sku) REFERENCES products (sku)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_sales_sku_date
    ON sales (sku, sale_date);

CREATE TABLE IF NOT EXISTS inventory (
    sku               TEXT PRIMARY KEY,
    on_hand           INTEGER NOT NULL CHECK (on_hand >= 0),
    updated_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (sku) REFERENCES products (sku)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS in_transit (
    shipment_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    sku               TEXT NOT NULL,
    quantity          INTEGER NOT NULL CHECK (quantity >= 0),
    expected_date     TEXT NOT NULL CHECK (expected_date = date(expected_date)),
    FOREIGN KEY (sku) REFERENCES products (sku)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_in_transit_sku_date
    ON in_transit (sku, expected_date);

CREATE TABLE IF NOT EXISTS stockouts (
    stockout_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    sku               TEXT NOT NULL,
    start_date        TEXT NOT NULL CHECK (start_date = date(start_date)),
    end_date          TEXT NOT NULL CHECK (end_date = date(end_date)),
    CHECK (end_date >= start_date),
    FOREIGN KEY (sku) REFERENCES products (sku)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_stockouts_sku_dates
    ON stockouts (sku, start_date, end_date);

-- One record per POST /api/v1/recalculate execution.
CREATE TABLE IF NOT EXISTS calculation_runs (
    run_id                    TEXT PRIMARY KEY,
    dataset                   TEXT NOT NULL CHECK (length(trim(dataset)) > 0),
    generated_at              TEXT NOT NULL,
    status                    TEXT NOT NULL CHECK (status IN ('completed', 'failed')),
    total_items               INTEGER NOT NULL DEFAULT 0 CHECK (total_items >= 0),
    total_units_to_order      INTEGER NOT NULL DEFAULT 0 CHECK (total_units_to_order >= 0),
    high_risk_items           INTEGER NOT NULL DEFAULT 0 CHECK (high_risk_items >= 0),
    anomalies_removed         INTEGER NOT NULL DEFAULT 0 CHECK (anomalies_removed >= 0),
    estimated_stockout_items  INTEGER NOT NULL DEFAULT 0 CHECK (estimated_stockout_items >= 0),
    error_message             TEXT
);

CREATE INDEX IF NOT EXISTS idx_calculation_runs_generated_at
    ON calculation_runs (generated_at DESC);

-- Request overrides are retained only for explainability and reproduction.
CREATE TABLE IF NOT EXISTS run_overrides (
    run_id            TEXT NOT NULL,
    sku               TEXT NOT NULL,
    on_hand           INTEGER CHECK (on_hand IS NULL OR on_hand >= 0),
    in_transit        INTEGER CHECK (in_transit IS NULL OR in_transit >= 0),
    PRIMARY KEY (run_id, sku),
    CHECK (on_hand IS NOT NULL OR in_transit IS NOT NULL),
    FOREIGN KEY (run_id) REFERENCES calculation_runs (run_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (sku) REFERENCES products (sku)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

-- Field names intentionally match docs/API_CONTRACT.md.
CREATE TABLE IF NOT EXISTS recommendations (
    run_id                     TEXT NOT NULL,
    sku                        TEXT NOT NULL,
    name                       TEXT NOT NULL,
    supplier_id                TEXT NOT NULL,
    supplier_name              TEXT NOT NULL,
    recommended_qty            INTEGER NOT NULL CHECK (recommended_qty >= 0),
    urgency                    TEXT NOT NULL CHECK (urgency IN ('high', 'medium', 'low')),
    on_hand                    INTEGER NOT NULL CHECK (on_hand >= 0),
    in_transit                 INTEGER NOT NULL CHECK (in_transit >= 0),
    lead_time_days             INTEGER NOT NULL CHECK (lead_time_days >= 0),
    avg_daily_demand           REAL NOT NULL CHECK (avg_daily_demand >= 0),
    forecast_demand            REAL NOT NULL CHECK (forecast_demand >= 0),
    safety_stock               REAL NOT NULL CHECK (safety_stock >= 0),
    seasonality_factor         REAL NOT NULL CHECK (seasonality_factor >= 0),
    growth_factor              REAL NOT NULL CHECK (growth_factor >= 0),
    stockout_compensation      REAL NOT NULL CHECK (stockout_compensation >= 0),
    outlier_units_removed      REAL NOT NULL CHECK (outlier_units_removed >= 0),
    days_of_cover              REAL NOT NULL CHECK (days_of_cover >= 0),
    reasons_json               TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (run_id, sku),
    FOREIGN KEY (run_id) REFERENCES calculation_runs (run_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (sku) REFERENCES products (sku)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (supplier_id) REFERENCES suppliers (supplier_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_recommendations_supplier_urgency
    ON recommendations (run_id, supplier_id, urgency);

CREATE TABLE IF NOT EXISTS agent_steps (
    run_id            TEXT NOT NULL,
    step_order        INTEGER NOT NULL CHECK (step_order BETWEEN 1 AND 7),
    step              TEXT NOT NULL CHECK (step IN (
        'load_data',
        'validate_data',
        'detect_outliers',
        'estimate_lost_demand',
        'calculate_recommendations',
        'validate_result',
        'save_result'
    )),
    status            TEXT NOT NULL CHECK (status IN ('completed', 'warning', 'failed')),
    message           TEXT NOT NULL,
    PRIMARY KEY (run_id, step_order),
    UNIQUE (run_id, step),
    FOREIGN KEY (run_id) REFERENCES calculation_runs (run_id)
        ON UPDATE CASCADE ON DELETE CASCADE
);

-- Derived timeline used by GET /api/v1/items/{sku}.
CREATE TABLE IF NOT EXISTS item_history (
    run_id                 TEXT NOT NULL,
    sku                    TEXT NOT NULL,
    history_date           TEXT NOT NULL CHECK (history_date = date(history_date)),
    units                  REAL NOT NULL CHECK (units >= 0),
    is_outlier             INTEGER NOT NULL CHECK (is_outlier IN (0, 1)),
    is_stockout            INTEGER NOT NULL CHECK (is_stockout IN (0, 1)),
    estimated_lost_units   REAL NOT NULL CHECK (estimated_lost_units >= 0),
    PRIMARY KEY (run_id, sku, history_date),
    FOREIGN KEY (run_id) REFERENCES calculation_runs (run_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (sku) REFERENCES products (sku)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

-- Recreate views so running init also applies compatible view migrations.
DROP VIEW IF EXISTS supplier_order_summary;
DROP VIEW IF EXISTS latest_recommendations;

-- Convenient views for VS Code SQLite viewers and manual demo inspection.
CREATE VIEW latest_recommendations AS
SELECT r.*
FROM recommendations AS r
JOIN (
    SELECT run_id
    FROM calculation_runs
    WHERE status = 'completed'
    -- rowid is the deterministic tie-breaker when the OS clock has coarse precision.
    ORDER BY generated_at DESC, rowid DESC
    LIMIT 1
) AS latest ON latest.run_id = r.run_id;

CREATE VIEW supplier_order_summary AS
SELECT
    supplier_id,
    supplier_name,
    COUNT(*) AS item_count,
    SUM(recommended_qty) AS total_units_to_order,
    SUM(CASE WHEN urgency = 'high' THEN 1 ELSE 0 END) AS high_risk_items
FROM latest_recommendations
GROUP BY supplier_id, supplier_name;

COMMIT;
