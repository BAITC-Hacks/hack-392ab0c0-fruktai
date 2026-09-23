PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id TEXT PRIMARY KEY,
    supplier_name TEXT NOT NULL,
    lead_time_days INTEGER NOT NULL CHECK (lead_time_days >= 0)
);
CREATE TABLE IF NOT EXISTS products (
    sku TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    supplier_id TEXT NOT NULL REFERENCES suppliers(supplier_id),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);
CREATE TABLE IF NOT EXISTS sales (
    sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_date TEXT NOT NULL,
    sku TEXT NOT NULL REFERENCES products(sku),
    units REAL NOT NULL CHECK (units >= 0)
);
CREATE INDEX IF NOT EXISTS idx_sales_sku_date ON sales(sku, sale_date);
CREATE TABLE IF NOT EXISTS inventory (
    sku TEXT PRIMARY KEY REFERENCES products(sku),
    on_hand REAL NOT NULL CHECK (on_hand >= 0),
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS in_transit (
    shipment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL REFERENCES products(sku),
    quantity REAL NOT NULL CHECK (quantity >= 0),
    expected_date TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_in_transit_sku_date ON in_transit(sku, expected_date);
CREATE TABLE IF NOT EXISTS stockouts (
    stockout_id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL REFERENCES products(sku),
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL CHECK (end_date >= start_date)
);
CREATE TABLE IF NOT EXISTS calculation_runs (
    run_id TEXT PRIMARY KEY,
    dataset TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('completed', 'failed')),
    total_items INTEGER NOT NULL CHECK (total_items >= 0),
    total_units_to_order REAL NOT NULL CHECK (total_units_to_order >= 0),
    high_risk_items INTEGER NOT NULL CHECK (high_risk_items >= 0),
    anomalies_removed REAL NOT NULL CHECK (anomalies_removed >= 0),
    estimated_stockout_items INTEGER NOT NULL CHECK (estimated_stockout_items >= 0)
);
CREATE INDEX IF NOT EXISTS idx_calculation_runs_generated_at ON calculation_runs(generated_at DESC);
CREATE TABLE IF NOT EXISTS run_overrides (
    run_id TEXT NOT NULL REFERENCES calculation_runs(run_id) ON DELETE CASCADE,
    sku TEXT NOT NULL REFERENCES products(sku),
    on_hand REAL,
    in_transit REAL,
    backorders REAL,
    reserved REAL,
    PRIMARY KEY(run_id, sku),
    CHECK(on_hand IS NOT NULL OR in_transit IS NOT NULL)
);
CREATE TABLE IF NOT EXISTS recommendations (
    run_id TEXT NOT NULL REFERENCES calculation_runs(run_id) ON DELETE CASCADE,
    sku TEXT NOT NULL REFERENCES products(sku),
    name TEXT NOT NULL,
    supplier_id TEXT NOT NULL REFERENCES suppliers(supplier_id),
    supplier_name TEXT NOT NULL,
    recommended_qty REAL NOT NULL CHECK(recommended_qty >= 0),
    urgency TEXT NOT NULL CHECK(urgency IN ('high', 'medium', 'low')),
    on_hand REAL NOT NULL CHECK(on_hand >= 0),
    in_transit REAL NOT NULL CHECK(in_transit >= 0),
    lead_time_days INTEGER NOT NULL CHECK(lead_time_days >= 0),
    avg_daily_demand REAL NOT NULL CHECK(avg_daily_demand >= 0),
    forecast_demand REAL NOT NULL CHECK(forecast_demand >= 0),
    safety_stock REAL NOT NULL CHECK(safety_stock >= 0),
    seasonality_factor REAL NOT NULL CHECK(seasonality_factor >= 0),
    growth_factor REAL NOT NULL CHECK(growth_factor >= 0),
    stockout_compensation REAL NOT NULL CHECK(stockout_compensation >= 0),
    outlier_units_removed REAL NOT NULL CHECK(outlier_units_removed >= 0),
    days_of_cover REAL NOT NULL CHECK(days_of_cover >= 0),
    reasons_json TEXT NOT NULL,
    calculation_json TEXT NOT NULL,
    PRIMARY KEY(run_id, sku)
);
CREATE TABLE IF NOT EXISTS approvals (
    run_id TEXT PRIMARY KEY REFERENCES calculation_runs(run_id) ON DELETE CASCADE,
    approved INTEGER NOT NULL CHECK(approved IN (0, 1)),
    note TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_steps (
    run_id TEXT NOT NULL REFERENCES calculation_runs(run_id) ON DELETE CASCADE,
    step_order INTEGER NOT NULL CHECK(step_order BETWEEN 1 AND 7),
    step TEXT NOT NULL CHECK(step IN ('load_data','validate_data','detect_outliers','estimate_lost_demand','calculate_recommendations','validate_result','save_result')),
    status TEXT NOT NULL CHECK(status IN ('completed','warning','failed')),
    message TEXT NOT NULL,
    PRIMARY KEY(run_id, step_order),
    UNIQUE(run_id, step)
);
CREATE TABLE IF NOT EXISTS item_history (
    run_id TEXT NOT NULL REFERENCES calculation_runs(run_id) ON DELETE CASCADE,
    sku TEXT NOT NULL REFERENCES products(sku),
    history_date TEXT NOT NULL,
    units REAL NOT NULL CHECK(units >= 0),
    is_outlier INTEGER NOT NULL CHECK(is_outlier IN (0, 1)),
    is_stockout INTEGER NOT NULL CHECK(is_stockout IN (0, 1)),
    estimated_lost_units REAL NOT NULL CHECK(estimated_lost_units >= 0),
    PRIMARY KEY(run_id, sku, history_date)
);
CREATE VIEW IF NOT EXISTS latest_recommendations AS
SELECT r.* FROM recommendations r JOIN (
    SELECT run_id FROM calculation_runs WHERE status='completed'
    ORDER BY generated_at DESC, rowid DESC LIMIT 1
) latest ON latest.run_id=r.run_id;
CREATE VIEW IF NOT EXISTS supplier_order_summary AS
SELECT supplier_id,supplier_name,COUNT(*) AS item_count,
       SUM(recommended_qty) AS total_units_to_order,
       SUM(CASE WHEN urgency='high' THEN 1 ELSE 0 END) AS high_risk_items
FROM latest_recommendations GROUP BY supplier_id,supplier_name;
