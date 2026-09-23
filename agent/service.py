"""Application service joining the deterministic workflow and SQLite audit log."""

from __future__ import annotations

import os
import json
import re
from pathlib import Path
from threading import Lock
from typing import Any

from database import (
    DatabaseError,
    RecordNotFoundError,
    latest_item_detail,
    load_csv_dataset,
    save_calculation,
)

from .openai_explainer import OpenAIExplainer, explanations_enabled
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
        explainer: OpenAIExplainer | None = None,
    ) -> None:
        self.data_root = Path(data_root)
        self.database_path = Path(database_path)
        self.output_dir = Path(output_dir) if output_dir is not None else None
        if safety_stock_days < 0:
            raise ValueError("safety_stock_days must be non-negative")
        self.safety_stock_days = safety_stock_days
        self.explainer = explainer
        self._recalculation_lock = Lock()

    @classmethod
    def from_environment(cls) -> "WorkflowService":
        """Build the backend singleton from documented environment variables."""

        try:
            safety_stock_days = int(os.getenv("FRUKTAI_SAFETY_STOCK_DAYS", "7"))
        except ValueError as error:
            raise ValueError("FRUKTAI_SAFETY_STOCK_DAYS must be an integer") from error
        return cls(
            data_root=os.getenv("FRUKTAI_DATA_ROOT", "data"),
            database_path=os.getenv("FRUKTAI_DATABASE_PATH", "artifacts/fruktai.sqlite"),
            output_dir=os.getenv("FRUKTAI_RUNS_DIR", "artifacts/runs"),
            safety_stock_days=safety_stock_days,
            explainer=(OpenAIExplainer.from_environment() if explanations_enabled() else None),
        )

    def recalculate(
        self,
        dataset: str,
        overrides: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Run, validate, persist, and return the fixed API response."""

        # One process may receive concurrent sync FastAPI requests. Serializing
        # the source sync + calculation + persistence keeps each run coherent.
        with self._recalculation_lock:
            dataset_path = self._resolve_dataset(dataset)
            execution = run_workflow_with_details(
                dataset_path,
                overrides=overrides or [],
                safety_stock_days=self.safety_stock_days,
                output_dir=self.output_dir,
            )
            response = execution.response
            item_details = execution.item_details
            manifest = dataset_path / "manifest.json"
            if manifest.is_file():
                metadata = json.loads(manifest.read_text(encoding="utf-8"))
                warnings = metadata.get("warnings", [])
                for item in response["recommendations"]:
                    reasons = ["Качество входных данных: " + warning for warning in warnings]
                    item["reasons"].extend(reasons)
                    # The orchestrator may share its reasons list with details.
                    detail_reasons = item_details[item["sku"]]["calculation"]["reasons"]
                    if detail_reasons is not item["reasons"]:
                        detail_reasons.extend(reasons)
            # Domain validation must happen before storage so invalid CSV data
            # becomes HTTP 422, while actual database failures remain HTTP 500.
            load_csv_dataset(self.database_path, dataset_path)
            if self.explainer is not None:
                response, item_details = self.explainer.enrich(
                    response,
                    item_details,
                )
            save_calculation(
                self.database_path,
                dataset,
                response,
                overrides=overrides or [],
                item_details=item_details,
            )
            return response

    def get_item(self, sku: str, run_id: str | None = None) -> dict[str, Any]:
        """Return latest persisted drill-down data for ``GET /items/{sku}``."""

        return latest_item_detail(self.database_path, sku, run_id)

    def _resolve_dataset(self, dataset: str) -> Path:
        if not isinstance(dataset, str) or DATASET_NAME.fullmatch(dataset) is None:
            raise DataValidationError("dataset may contain only Latin letters, digits, '_' and '-'")
        root = self.data_root.resolve()
        if dataset.startswith("upload_"):
            root = self.database_path.parent.resolve() / "imports"
        candidate = (root / dataset).resolve()
        if not candidate.is_relative_to(root):
            raise DataValidationError("dataset path escapes the configured data root")
        if not candidate.is_dir():
            raise DatasetNotFoundError(f"Dataset not found: {dataset}")
        return candidate


__all__ = [
    "DatasetNotFoundError",
    "DatabaseError",
    "RecordNotFoundError",
    "WorkflowService",
]
