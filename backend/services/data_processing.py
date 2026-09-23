from __future__ import annotations

import numpy as np
import pandas as pd


def _bool(value: object) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "y", "да"}


def build_daily_demand_series(
    sales: pd.DataFrame, products: pd.DataFrame | None = None, stockouts: pd.DataFrame | None = None
) -> pd.DataFrame:
    """Create a regular calendar-day demand layer without changing input frames."""
    required = {"date", "sku", "quantity"}
    missing = required - set(sales.columns)
    if missing:
        raise ValueError(f"sales missing required columns: {sorted(missing)}")
    src = sales.copy()
    src["date"] = pd.to_datetime(src["date"], errors="coerce", utc=True).dt.tz_convert(None).dt.normalize()
    if src["date"].isna().any():
        raise ValueError("invalid sales dates")
    src["sku"] = src["sku"].astype(str).str.strip().str.upper()
    src["quantity"] = pd.to_numeric(src["quantity"], errors="coerce")
    if src["quantity"].isna().any() or (src["quantity"] < 0).any():
        raise ValueError("quantity must be non-negative numeric")
    if "is_return" in src:
        src = src.loc[~src["is_return"].map(_bool)].copy()
    grouped = src.groupby(["sku", "date"], as_index=False, sort=True)["quantity"].sum().rename(columns={"quantity": "raw_demand"})
    if grouped.empty:
        return pd.DataFrame(columns=["date", "sku", "raw_demand", "is_stockout", "is_available", "regular_demand", "estimated_lost_demand", "corrected_demand"])
    sku_values = set(grouped.sku)
    if products is not None and "sku" in products:
        sku_values |= set(products.sku.astype(str).str.strip().str.upper())
    rows = []
    for sku in sorted(sku_values):
        part = grouped[grouped.sku == sku]
        if part.empty:
            continue
        dates = pd.date_range(part.date.min(), part.date.max(), freq="D")
        base = pd.DataFrame({"date": dates})
        base["sku"] = sku
        base = base.merge(part, on=["sku", "date"], how="left").fillna({"raw_demand": 0.0})
        base["is_stockout"] = False
        if stockouts is not None and not stockouts.empty:
            st = stockouts.copy()
            st["sku"] = st["sku"].astype(str).str.strip().str.upper()
            if "date" in st:
                st["date"] = pd.to_datetime(st["date"], errors="coerce").dt.normalize()
                dates_out = set(st.loc[(st.sku == sku) & st.date.notna(), "date"])
                base["is_stockout"] = base.date.isin(dates_out)
            elif {"start_date", "end_date"} <= set(st.columns):
                for row in st.loc[st.sku == sku].itertuples():
                    base.loc[base.date.between(pd.Timestamp(row.start_date), pd.Timestamp(row.end_date)), "is_stockout"] = True
        base["is_available"] = ~base["is_stockout"]
        base["regular_demand"] = base["raw_demand"]
        base["estimated_lost_demand"] = 0.0
        base["corrected_demand"] = base["regular_demand"]
        rows.append(base)
    return pd.concat(rows, ignore_index=True).sort_values(["sku", "date"], kind="mergesort").reset_index(drop=True)


def detect_transaction_outliers(sales: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Detect one-sided SKU/customer/day outliers and retain all source rows."""
    src = sales.copy()
    src["date"] = pd.to_datetime(src["date"], errors="coerce").dt.normalize()
    src["sku"] = src["sku"].astype(str).str.strip().str.upper()
    src["customer_id"] = src.get("customer_id", pd.Series("unknown", index=src.index)).fillna("unknown").astype(str)
    src["quantity"] = pd.to_numeric(src["quantity"], errors="raise")
    agg = src.groupby(["sku", "customer_id", "date"], as_index=False, sort=True)["quantity"].sum()
    agg["is_outlier"] = False
    agg["outlier_method"] = "none"
    agg["outlier_score"] = 0.0
    agg["outlier_threshold"] = np.nan
    agg["customer_share"] = 0.0
    for sku, idx in agg.groupby("sku", sort=True).groups.items():
        part = agg.loc[idx, "quantity"]
        median = float(part.median())
        mad = float(np.median(np.abs(part - median)))
        if mad > 0:
            score = 0.6745 * (part - median) / mad
            threshold = median + 3.5 * mad / 0.6745
            mask = score > 3.5
            method = "modified_z_mad"
        else:
            q1, q3 = part.quantile([0.25, 0.75])
            iqr = float(q3 - q1)
            threshold = float(q3 + 1.5 * iqr)
            score = pd.Series(0.0, index=part.index)
            mask = part > threshold if iqr > 0 else part > max(float(q3), 0.0) * 3
            method = "iqr_fallback"
        daily_total = agg.loc[idx].groupby("date")["quantity"].transform("sum")
        share = part / daily_total.to_numpy()
        agg.loc[idx, "outlier_score"] = score
        agg.loc[idx, "outlier_threshold"] = threshold
        agg.loc[idx, "customer_share"] = share
        agg.loc[idx, "is_outlier"] = mask.to_numpy() & (share.to_numpy() >= 0.8)
        agg.loc[idx, "outlier_method"] = method
    agg["excluded_from_regular_demand"] = agg.is_outlier
    annotated = src.merge(agg, on=["sku", "customer_id", "date"], how="left", suffixes=("", "_aggregate"))
    summary = agg.loc[agg.is_outlier].copy()
    return annotated, summary


def estimate_lost_demand(daily_demand: pd.DataFrame) -> pd.DataFrame:
    """Estimate stockout demand using only prior available, non-outlier observations."""
    out = daily_demand.copy().sort_values(["sku", "date"], kind="mergesort")
    if "regular_demand" not in out:
        out["regular_demand"] = out["raw_demand"]
    if "is_stockout" not in out:
        out["is_stockout"] = False
    out["estimated_lost_demand"] = 0.0
    for sku, idx in out.groupby("sku", sort=True).groups.items():
        positions = list(idx)
        for pos, row_idx in enumerate(positions):
            row = out.loc[row_idx]
            if not bool(row.is_stockout):
                continue
            history = out.loc[positions[:pos]]
            history = history.loc[~history.is_stockout]
            if "is_outlier" in history:
                history = history.loc[~history.is_outlier]
            same_weekday = history.loc[history.date.dt.dayofweek == row.date.dayofweek, "regular_demand"]
            candidates = same_weekday.tail(8)
            if len(candidates) < 3:
                candidates = history.loc[history.regular_demand > 0].tail(28).regular_demand
            estimate = float(candidates.median()) if len(candidates) else 0.0
            out.loc[row_idx, "estimated_lost_demand"] = max(0.0, estimate - float(row.raw_demand))
            out.loc[row_idx, "corrected_demand"] = max(float(row.regular_demand), estimate)
    out["corrected_demand"] = np.where(out.is_stockout, out["regular_demand"] + out["estimated_lost_demand"], out["regular_demand"])
    return out.reset_index(drop=True)
