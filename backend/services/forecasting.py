from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd


def seasonal_naive_forecast(series: pd.Series, horizon: int, season: int = 7) -> np.ndarray:
    values = np.asarray(series, dtype=float)
    if len(values) < season * 2:
        return np.repeat(
            float(np.median(values[-min(28, len(values)) :])) if len(values) else 0.0, horizon
        )
    return np.array([values[-season + (i % season)] for i in range(horizon)], dtype=float)


def median_baseline(series: pd.Series, horizon: int) -> np.ndarray:
    return np.repeat(
        float(np.median(np.asarray(series, dtype=float)[-28:])) if len(series) else 0.0, horizon
    )


def sba_forecast(series: pd.Series, horizon: int, alpha: float = 0.1) -> np.ndarray:
    values = np.asarray(series, dtype=float)
    nonzero = np.flatnonzero(values > 0)
    if len(nonzero) == 0:
        return np.zeros(horizon)
    size, interval = values[nonzero[0]], max(1, nonzero[0] + 1)
    last = nonzero[0]
    for pos in nonzero[1:]:
        gap = pos - last
        size = alpha * values[pos] + (1 - alpha) * size
        interval = alpha * gap + (1 - alpha) * interval
        last = pos
    return np.repeat(max(0.0, (1 - alpha / 2) * size / max(interval, 1e-12)), horizon)


@dataclass
class BacktestResult:
    metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    selected_model: str = "median_baseline"


def _metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    error = actual - predicted
    denom = float(np.abs(actual).sum())
    return {
        "mae": float(np.abs(error).mean()) if len(error) else 0.0,
        "rmse": float(np.sqrt(np.mean(error**2))) if len(error) else 0.0,
        "wape": float(np.abs(error).sum() / denom) if denom > 0 else float("nan"),
        "bias": float((predicted - actual).sum() / actual.sum()) if actual.sum() else float("nan"),
    }


def rolling_origin_backtest(
    series: pd.Series,
    candidate_models: list[tuple[str, Callable[[pd.Series, int], np.ndarray]]] | list[Callable],
    horizon: int,
) -> BacktestResult:
    values = np.asarray(series, dtype=float)
    result = BacktestResult()
    min_train = max(14, horizon * 2)
    for index, candidate in enumerate(candidate_models):
        name, fn = (
            candidate
            if isinstance(candidate, tuple)
            else (getattr(candidate, "__name__", f"model_{index}"), candidate)
        )
        actuals, preds = [], []
        for end in range(min_train, len(values) - horizon + 1, max(1, horizon)):
            actual = values[end : end + horizon]
            pred = np.asarray(fn(pd.Series(values[:end]), horizon), dtype=float)
            actuals.extend(actual)
            preds.extend(pred[: len(actual)])
        result.metrics[name] = (
            _metrics(np.asarray(actuals), np.asarray(preds))
            if actuals
            else {
                "mae": float("inf"),
                "rmse": float("inf"),
                "wape": float("inf"),
                "bias": float("nan"),
            }
        )
    if result.metrics:
        result.selected_model = min(
            result.metrics,
            key=lambda name: (
                np.nan_to_num(result.metrics[name]["wape"], nan=np.inf),
                result.metrics[name]["mae"],
            ),
        )
    return result
