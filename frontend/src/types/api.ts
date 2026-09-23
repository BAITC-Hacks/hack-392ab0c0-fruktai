export interface Override {
  sku: string;
  on_hand?: number;
  in_transit?: number;
}
export interface ImportMetadata {
  dataset: string;
  source: 'file_upload' | '1c_file_exchange';
  warehouse_id: string;
  counts: Record<string, number>;
  warnings: string[];
  preview: Record<string, Record<string, string>[]>;
  products: { sku: string; name: string; category: string; unit: string }[];
}
export interface Calculation {
  recommended_qty: number;
  on_hand: number;
  in_transit: number;
  lead_time_days: number;
  avg_daily_demand: number;
  forecast_demand: number;
  safety_stock: number;
  seasonality_factor: number;
  growth_factor: number;
  stockout_compensation: number;
  outlier_units_removed: number;
  days_of_cover: number;
  reasons: string[];
}
export interface Recommendation extends Calculation {
  sku: string;
  name: string;
  supplier_id: string;
  supplier_name: string;
  urgency: 'high' | 'medium' | 'low';
}
export interface AgentStep {
  step: string;
  status: 'completed' | 'warning' | 'failed';
  message: string;
}
export interface RecalculateResponse {
  run_id: string;
  generated_at: string;
  summary: {
    total_items: number;
    total_units_to_order: number;
    high_risk_items: number;
    anomalies_removed: number;
    estimated_stockout_items: number;
  };
  recommendations: Recommendation[];
  agent_steps: AgentStep[];
}
export interface ItemResponse {
  sku: string;
  name: string;
  calculation: Calculation;
  history: {
    date: string;
    units: number;
    is_outlier: boolean;
    is_stockout: boolean;
    estimated_lost_units: number;
  }[];
}
