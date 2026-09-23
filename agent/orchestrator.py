"""Public, backward-compatible orchestration facade for the seven workflow steps."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .workflow import data, demand, recommendations, results
from .workflow.models import (
    DataValidationError,
    REQUIRED_FILES,
    WORKFLOW_STEPS,
    WorkflowState,
    WorkflowExecution,
)


class ReplenishmentOrchestrator:
    def __init__(self, safety_stock_days: int = 7, output_dir: str | Path | None = None):
        if safety_stock_days < 0:
            raise ValueError("safety_stock_days must be non-negative")
        self.safety_stock_days = safety_stock_days
        configured_dir = os.getenv("FRUKTAI_RUNS_DIR", "artifacts/runs")
        self.output_dir = Path(output_dir or configured_dir)
        self.steps: list[dict[str, str]] = []

    def run(
        self,
        dataset_path: str | Path,
        overrides: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return self.run_with_details(dataset_path, overrides).response

    def run_with_details(
        self,
        dataset_path: str | Path,
        overrides: list[dict[str, Any]] | None = None,
    ) -> WorkflowExecution:
        self.steps = []
        state = WorkflowState(dataset_path=Path(dataset_path))
        run_id = str(uuid4())
        generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        try:
            self._run_step("load_data", lambda: self.load_data(state))
            self._run_step("validate_data", lambda: self.validate_data(state, overrides or []))
            self._run_step("detect_outliers", lambda: self.detect_outliers(state))
            self._run_step("estimate_lost_demand", lambda: self.estimate_lost_demand(state))
            self._run_step(
                "calculate_recommendations",
                lambda: self.calculate_recommendations(state),
            )
            result = results._build_result(run_id, generated_at, state, self.steps)
            item_details = results._build_item_details(state)
            self._run_step(
                "validate_result",
                lambda: self.validate_result(result, item_details),
            )
            # save_result must be present in the persisted and returned journal.
            self.steps.append(
                {
                    "step": "save_result",
                    "status": "completed",
                    "message": f"Saved calculation run {run_id}",
                }
            )
            result["agent_steps"] = list(self.steps)
            self.save_result(result)
            return WorkflowExecution(response=result, item_details=item_details)
        except Exception as error:
            current_step = WORKFLOW_STEPS[min(len(self.steps), len(WORKFLOW_STEPS) - 1)]
            if not self.steps or self.steps[-1].get("status") != "failed":
                self.steps.append({"step": current_step, "status": "failed", "message": str(error)})
            self._save_failure_log(run_id, generated_at, error)
            raise

    def _run_step(self, step: str, operation: Any) -> None:
        try:
            message = operation()
        except Exception as error:
            self.steps.append({"step": step, "status": "failed", "message": str(error)})
            raise
        self.steps.append({"step": step, "status": "completed", "message": str(message)})

    def save_result(self, result: dict[str, Any]) -> str:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        destination = self.output_dir / f"{result['run_id']}.json"
        with destination.open("w", encoding="utf-8") as target:
            json.dump(result, target, ensure_ascii=False, indent=2, allow_nan=False)
            target.write("\n")
        return str(destination)

    def _save_failure_log(self, run_id: str, generated_at: str, error: Exception) -> None:
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            path = self.output_dir / f"{run_id}.failed.json"
            payload = {
                "run_id": run_id,
                "generated_at": generated_at,
                "error": str(error),
                "agent_steps": self.steps,
            }
            with path.open("w", encoding="utf-8") as target:
                json.dump(payload, target, ensure_ascii=False, indent=2, allow_nan=False)
                target.write("\n")
        except OSError:
            # Preserve the original data/calculation failure.
            return

    def load_data(self, state: WorkflowState) -> str:
        return data.load_data(state)

    def validate_data(self, state: WorkflowState, overrides: list[dict[str, Any]]) -> str:
        return data.validate_data(state, overrides)

    def detect_outliers(self, state: WorkflowState) -> str:
        return demand.detect_outliers(state)

    def estimate_lost_demand(self, state: WorkflowState) -> str:
        return demand.estimate_lost_demand(state)

    def calculate_recommendations(self, state: WorkflowState) -> str:
        return recommendations.calculate_recommendations(state, self.safety_stock_days)

    def validate_result(self, result: dict[str, Any], item_details=None) -> str:
        return results.validate_result(result, item_details)


def run_workflow(
    dataset_path: str | Path,
    overrides: list[dict[str, Any]] | None = None,
    *,
    safety_stock_days: int = 7,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Run the complete workflow and return an API-compatible response."""

    return run_workflow_with_details(
        dataset_path=dataset_path,
        overrides=overrides,
        safety_stock_days=safety_stock_days,
        output_dir=output_dir,
    ).response


def run_workflow_with_details(
    dataset_path: str | Path,
    overrides: list[dict[str, Any]] | None = None,
    *,
    safety_stock_days: int = 7,
    output_dir: str | Path | None = None,
) -> WorkflowExecution:
    """Run the workflow and retain item drill-down data for persistence."""

    return ReplenishmentOrchestrator(
        safety_stock_days=safety_stock_days,
        output_dir=output_dir,
    ).run_with_details(dataset_path=dataset_path, overrides=overrides)


__all__ = [
    "DataValidationError",
    "REQUIRED_FILES",
    "WORKFLOW_STEPS",
    "WorkflowState",
    "WorkflowExecution",
    "ReplenishmentOrchestrator",
    "run_workflow",
    "run_workflow_with_details",
]
