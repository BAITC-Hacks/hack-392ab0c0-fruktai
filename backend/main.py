"""HTTP adapter for the shared calculation, AI explanation and SQLite service."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from agent import (
    DataValidationError, DatabaseError, DatasetNotFoundError,
    RecordNotFoundError, WorkflowService,
)
from database import initialize_database
from .schemas import (
    HealthResponse, RecalculateRequest, ContractRecalculateResponse,
    ContractItemResponse,
)

LOGGER = logging.getLogger(__name__)


def create_app(service: WorkflowService | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.workflow = service or WorkflowService.from_environment()
        initialize_database(app.state.workflow.database_path)
        yield

    app = FastAPI(title="FruktAI integrated API", version="1.0.0", lifespan=lifespan)

    @app.get("/health", response_model=HealthResponse)
    def health():
        return {"status": "ok"}

    @app.post("/api/v1/recalculate", response_model=ContractRecalculateResponse)
    def recalculate(payload: RecalculateRequest, request: Request):
        try:
            return request.app.state.workflow.recalculate(
                payload.dataset,
                [value.model_dump(exclude_none=True) for value in payload.overrides],
            )
        except DatasetNotFoundError as error:
            raise HTTPException(404, str(error)) from error
        except DataValidationError as error:
            raise HTTPException(422, str(error)) from error
        except DatabaseError as error:
            # Storage failures are server errors, not invalid user input.
            LOGGER.exception("Calculation persistence failed")
            raise HTTPException(500, "Calculation storage failed") from error

    @app.get("/api/v1/items/{sku}", response_model=ContractItemResponse)
    def item(sku: str, request: Request):
        try:
            return request.app.state.workflow.get_item(sku)
        except RecordNotFoundError as error:
            raise HTTPException(404, "No calculated item found for this SKU") from error
        except DatabaseError as error:
            LOGGER.exception("Item storage read failed")
            raise HTTPException(500, "Item storage read failed") from error

    return app


app = create_app()
