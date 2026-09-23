"""HTTP adapter for the shared calculation, AI explanation and SQLite service."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form, Query
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from agent import (
    DataValidationError,
    DatabaseError,
    DatasetNotFoundError,
    RecordNotFoundError,
    WorkflowService,
)
from database import initialize_database
from .imports import import_dataset, read_metadata, ImportProblem, MAX_FILE, MAX_TOTAL
from .exports import export_run, template_workbook
from .schemas import (
    HealthResponse,
    RecalculateRequest,
    ContractRecalculateResponse,
    ContractItemResponse,
)

LOGGER = logging.getLogger(__name__)


def create_app(service: WorkflowService | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.workflow = service or WorkflowService.from_environment()
        initialize_database(app.state.workflow.database_path)
        yield

    app = FastAPI(title="FruktAI integrated API", version="1.1.0", lifespan=lifespan)

    @app.get("/health", response_model=HealthResponse)
    def health():
        return {"status": "ok"}

    @app.get("/api/v1/datasets/template.xlsx")
    def template():
        return Response(
            template_workbook(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="fruktai-input-template.xlsx"'},
        )

    @app.post("/api/v1/datasets/import", status_code=201)
    async def upload(
        request: Request,
        files: list[UploadFile] = File(...),
        anonymized: bool = Form(False),
        warehouse_id: str = Form(""),
    ):
        try:
            if len(files) > 12:
                raise ImportProblem("Максимум 12 файлов", 413)
            buffers = []
            total = 0
            for file in files:
                content = await file.read(MAX_FILE + 1)
                total += len(content)
                if len(content) > MAX_FILE or total > MAX_TOTAL:
                    raise ImportProblem("Лимит: 10 MiB на файл, 30 MiB суммарно", 413)
                buffers.append((file.filename or "", content))
            workflow = request.app.state.workflow
            return await run_in_threadpool(
                import_dataset,
                buffers,
                workflow.database_path.parent / "imports",
                workflow.database_path,
                anonymized=anonymized,
                warehouse_id=warehouse_id,
            )
        except ImportProblem as error:
            raise HTTPException(error.status, str(error)) from error
        finally:
            for file in files:
                await file.close()

    @app.get("/api/v1/datasets/{dataset}")
    def dataset_metadata(dataset: str, request: Request):
        try:
            return read_metadata(request.app.state.workflow.database_path, dataset)
        except ImportProblem as error:
            raise HTTPException(error.status, str(error)) from error

    @app.get("/api/v1/runs/{run_id}/export")
    def export(
        run_id: str, request: Request, format: str = "csv", sku: list[str] = Query(default=[])
    ):
        try:
            content, media = export_run(
                request.app.state.workflow.database_path, run_id, format, sku
            )
            return Response(
                content,
                media_type=media,
                headers={
                    "Content-Disposition": f'attachment; filename="fruktai-recommendations.{format}"'
                },
            )
        except ImportProblem as error:
            raise HTTPException(error.status, str(error)) from error

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
    def item(sku: str, request: Request, run_id: str | None = None):
        try:
            return request.app.state.workflow.get_item(sku, run_id)
        except RecordNotFoundError as error:
            raise HTTPException(404, "No calculated item found for this SKU") from error
        except DatabaseError as error:
            LOGGER.exception("Item storage read failed")
            raise HTTPException(500, "Item storage read failed") from error

    return app


app = create_app()
