"""Application service joining the deterministic workflow and SQLite audit log."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from database import (
    RecordNotFoundError,
    latest_item_detail,
    load_csv_dataset,
    save_calculation,
)

from .orchestrator import DataValidationError, run_workflow_with_details


DATASET_NAME = re.compile(r"^[A-Za-z0-9_-]+$")


class DatasetNotFoundError(FileNotFoundError):
    """Raised when a valid dataset name has no source directory."""


class WorkflowService:
    """Backend-facing entry point for recalculation and item drill-down."""

    def __init__(
        self,
        data_root: str | Path,
        database_path: str | Path,
        output_dir: str | Path | None = None,
        safety_stock_days: int = 7,
    ) -> None:
        self.data_root = Path(data_root)
        self.database_path = Path(database_path)
        self.output_dir = Path(output_dir) if output_dir is not None else None
        if safety_stock_days < 0:
            raise ValueError("safety_stock_days must be non-negative")
        self.safety_stock_days = safety_stock_days

    def recalculate(
        self,
        dataset: str,
        overrides: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Run, validate, persist, and return the fixed API response."""

        dataset_path = self._resolve_dataset(dataset)
        # Store only source rows that passed the database boundary validation.
        load_csv_dataset(self.database_path, dataset_path)
        execution = run_workflow_with_details(
            dataset_path,
            overrides=overrides or [],
            safety_stock_days=self.safety_stock_days,
            output_dir=self.output_dir,
        )
        save_calculation(
            self.database_path,
            dataset,
            execution.response,
            overrides=overrides or [],
            item_details=execution.item_details,
        )
        return execution.response

    def get_item(self, sku: str) -> dict[str, Any]:
        """Return latest persisted drill-down data for ``GET /items/{sku}``."""

        return latest_item_detail(self.database_path, sku)

    def _resolve_dataset(self, dataset: str) -> Path:
        if not isinstance(dataset, str) or DATASET_NAME.fullmatch(dataset) is None:
            raise DataValidationError(
                "dataset may contain only Latin letters, digits, '_' and '-'"
            )
        root = self.data_root.resolve()
        candidate = (root / dataset).resolve()
        if not candidate.is_relative_to(root):
            raise DataValidationError("dataset path escapes the configured data root")
        if not candidate.is_dir():
            raise DatasetNotFoundError(f"Dataset not found: {dataset}")
        return candidate


__all__ = [
    "DatasetNotFoundError",
    "RecordNotFoundError",
    "WorkflowService",
]

