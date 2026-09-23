"""Validated source publication and metadata access; parser API stays compatible."""

import csv
from datetime import date
import json
from pathlib import Path
import tempfile
from uuid import uuid4

from agent.orchestrator import ReplenishmentOrchestrator, WorkflowState, REQUIRED_FILES
from database.repository import connect, initialize_database
from .file_exchange.normalization import ImportProblem, MAX_FILE, MAX_TOTAL, MAX_ROWS, OPTIONAL
from .file_exchange.parsers import parse_file


def select_warehouse(tables, selected):
    scoped = ("sales", "inventory", "material_statement", "stockouts", "in_transit")
    warehouses = {
        r.get("warehouse_id", "")
        for t in scoped
        for r in tables.get(t, [])
        if r.get("warehouse_id")
    }
    if len(warehouses) > 1 and not selected:
        raise ImportProblem(
            "Обнаружено несколько складов. Укажите warehouse_id: " + ", ".join(sorted(warehouses))
        )
    chosen = selected or next(iter(warehouses), "")
    if selected and selected not in warehouses:
        raise ImportProblem("Указанный склад отсутствует в данных")
    for name in scoped:
        rows = tables.get(name, [])
        if warehouses and any(not r.get("warehouse_id") for r in rows):
            raise ImportProblem(f"{name}: заполните склад во всех строках для однозначного расчёта")
        if chosen and name in tables:
            tables[name] = [r for r in rows if r.get("warehouse_id") == chosen]
    return chosen


def import_dataset(
    files, data_root: Path, database_path: Path, *, anonymized: bool, warehouse_id=""
):
    if not anonymized:
        raise ImportProblem("Подтвердите, что клиентские данные уже обезличены")
    if not 1 <= len(files) <= 12:
        raise ImportProblem("Загрузите от 1 до 12 файлов", 413)
    if sum(len(content) for _, content in files) > MAX_TOTAL:
        raise ImportProblem("Общий размер файлов превышает 30 MiB", 413)
    tables = {}
    for name, content in files:
        if not content or len(content) > MAX_FILE:
            raise ImportProblem("Пустой файл или размер больше 10 MiB", 413)
        for key, rows in parse_file(name, content).items():
            if key in tables:
                raise ImportProblem(f"Таблица {key} загружена несколько раз")
            tables[key] = rows
    if sum(map(len, tables.values())) > MAX_ROWS:
        raise ImportProblem("Общее количество строк превышает 50000", 413)
    # Bound expansion into daily stockout observations before workflow validation.
    expanded_days = 0
    for row in tables.get("stockouts", []):
        try:
            expanded_days += max(
                0,
                (date.fromisoformat(row["end_date"]) - date.fromisoformat(row["start_date"])).days
                + 1,
            )
        except ValueError:
            raise ImportProblem("stockouts: заполните даты начала и окончания")
    if expanded_days > 100_000:
        raise ImportProblem("Stockout-периоды превышают лимит 100000 дней суммарно", 413)
    warehouse = select_warehouse(tables, warehouse_id.strip())
    warnings = []
    if "material_statement" in tables:

        def balances(rows):
            result = {}
            for row in rows:
                if row["sku"] in result:
                    raise ImportProblem(
                        "Повторный артикул в остатках: требуется один конечный остаток"
                    )
                result[row["sku"]] = row["on_hand"]
            return result

        material = balances(tables["material_statement"])
        if "inventory" in tables and balances(tables["inventory"]) != material:
            raise ImportProblem("Остатки inventory расходятся с материальной ведомостью 1С")
        tables["inventory"] = [dict(r) for r in tables["material_statement"]]
    for name in ("stockouts", "in_transit"):
        if name not in tables:
            tables[name] = []
            warnings.append(f"{name} не загружен: использованы нулевые события. Проверьте полноту.")
    missing = set(REQUIRED_FILES) - set(tables)
    if missing:
        raise ImportProblem("Не хватает таблиц: " + ", ".join(sorted(missing)))
    if not tables["sales"] or not tables["products"] or not tables["inventory"]:
        raise ImportProblem("Для выбранного склада нужны продажи, товары и остатки")
    if warehouse:
        active_skus = {r["sku"] for r in tables["inventory"]}
        tables["products"] = [r for r in tables["products"] if r["sku"] in active_skus]
    for field in ("customer_id", "price"):
        if any(not row.get(field) for row in tables["sales"]):
            warnings.append(
                f"sales.{field}: есть пропуски; значения не придуманы, проверьте исходную выгрузку."
            )
    if not warehouse:
        warnings.append("Склад не указан: набор считается одним складом.")
    dataset = "upload_" + uuid4().hex
    data_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".import-", dir=data_root) as temp:
        folder = Path(temp)
        for name, headers in REQUIRED_FILES.items():
            fields = list(headers) + [
                f for f in OPTIONAL[name] if any(f in r for r in tables[name])
            ]
            with (folder / f"{name}.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(tables[name])
        orchestrator = ReplenishmentOrchestrator(output_dir=folder / "unused")
        state = WorkflowState(dataset_path=folder)
        try:
            orchestrator.load_data(state)
            orchestrator.validate_data(state, [])
        except ValueError as error:
            raise ImportProblem(str(error)) from error
        metadata = {
            "dataset": dataset,
            "source": "1c_file_exchange" if "material_statement" in tables else "file_upload",
            "warehouse_id": warehouse,
            "counts": {key: len(value) for key, value in tables.items()},
            "warnings": warnings,
            "preview": {
                key: [{k: v for k, v in row.items() if k != "customer_id"} for row in value[:5]]
                for key, value in tables.items()
            },
            "products": [
                {k: row.get(k, "") for k in ("sku", "name", "category", "unit")}
                for row in tables["products"]
            ],
        }
        (folder / "manifest.json").write_text(
            json.dumps(metadata, ensure_ascii=False), encoding="utf-8"
        )
        # Normalized snapshot includes supplied price/customer/warehouse fields.
        # Published IDs are random and paths never come from uploaded filenames.
        initialize_database(database_path)
        with connect(database_path) as db:
            db.execute(
                "INSERT INTO source_imports(dataset, metadata_json, tables_json) VALUES (?, ?, ?)",
                (
                    dataset,
                    json.dumps(metadata, ensure_ascii=False),
                    json.dumps(tables, ensure_ascii=False),
                ),
            )
            destination = data_root / dataset
            folder.rename(destination)
    return metadata


def read_metadata(database_path, dataset):
    with connect(database_path) as db:
        row = db.execute(
            "SELECT metadata_json FROM source_imports WHERE dataset=?", (dataset,)
        ).fetchone()
    if row is None:
        raise ImportProblem("Набор не найден", 404)
    return json.loads(row["metadata_json"])
