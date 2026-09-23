"""Deterministic file-exchange boundary; never asks an LLM to invent input data."""
from __future__ import annotations

import csv
from datetime import date, datetime
from io import BytesIO, StringIO
import json
import math
from pathlib import Path
import re
import tempfile
from uuid import uuid4
import zipfile

from agent.orchestrator import ReplenishmentOrchestrator, WorkflowState, REQUIRED_FILES
from database.repository import connect, initialize_database

MAX_FILE = 10 * 1024 * 1024
MAX_TOTAL = 30 * 1024 * 1024
MAX_ROWS = 50_000
OPTIONAL = {
    "sales": ("customer_id", "price", "warehouse_id"),
    "products": ("category", "unit"),
    "inventory": ("warehouse_id",),
    "stockouts": ("warehouse_id",),
    "in_transit": ("warehouse_id",),
    "suppliers": (),
    "material_statement": ("warehouse_id",),
}
REQUIRED = dict(REQUIRED_FILES, material_statement=("sku", "on_hand"))
TABLE_NAMES = {
    "продажи": "sales", "товары": "products", "поставщики": "suppliers",
    "остатки": "inventory", "отсутствие": "stockouts", "в пути": "in_transit",
    "материальная ведомость": "material_statement",
}
ALIASES = {
    "дата": "date", "артикул": "sku", "количество": "units",
    "обезличенный клиент": "customer_id", "цена": "price", "склад": "warehouse_id",
    "наименование": "name", "код поставщика": "supplier_id", "поставщик": "supplier_name",
    "срок поставки": "lead_time_days", "срок поставки дней": "lead_time_days",
    "остаток": "on_hand", "конечный остаток": "on_hand", "активен": "active",
    "дата начала": "start_date", "дата окончания": "end_date",
    "ожидаемая дата": "expected_date", "категория": "category", "единица": "unit",
}
NUMBERS = {"units", "price", "quantity", "on_hand", "lead_time_days"}
DATES = {"date", "start_date", "end_date", "expected_date"}


class ImportProblem(ValueError):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


def table_name(value):
    key = str(value).strip().lower()
    key = TABLE_NAMES.get(key, key)
    if key not in REQUIRED:
        raise ImportProblem(f"Неизвестная таблица «{value}». Используйте имена листов из шаблона.")
    return key


def cell(value):
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def normalize(table, matrix):
    if not matrix:
        raise ImportProblem(f"{table}: отсутствует строка заголовков")
    raw_header = [cell(v).strip().lower() for v in matrix[0]]
    headers = [ALIASES.get(v, v) for v in raw_header]
    if table == "in_transit":
        headers = ["quantity" if h == "units" else h for h in headers]
    if len(set(headers)) != len(headers) or any(not h for h in headers):
        raise ImportProblem(f"{table}: пустые или повторяющиеся заголовки")
    unknown = set(headers) - set(REQUIRED[table]) - set(OPTIONAL[table])
    if unknown:
        raise ImportProblem(f"{table}: неизвестные колонки {', '.join(sorted(unknown))}. Сверьте шаблон; не загружайте персональные данные.")
    missing = set(REQUIRED[table]) - set(headers)
    if missing:
        raise ImportProblem(f"{table}: отсутствуют колонки {', '.join(sorted(missing))}")
    rows = []
    for index, raw in enumerate(matrix[1:], 2):
        values = [cell(v) for v in raw]
        if not any(values):
            continue
        if len(values) != len(headers):
            raise ImportProblem(f"{table}, строка {index}: число ячеек не совпадает с заголовками")
        if [v.lower() for v in values] == raw_header:
            continue  # repeated PDF page header
        row = dict(zip(headers, values))
        for key, value in row.items():
            if len(value) > 1000:
                raise ImportProblem(f"{table}, строка {index}: слишком длинное значение")
            if key in NUMBERS and value:
                try:
                    numeric = float(value.replace("\u00a0", "").replace(" ", "").replace(",", "."))
                except ValueError:
                    raise ImportProblem(f"{table}, строка {index}: {key} должно быть числом")
                if not math.isfinite(numeric) or numeric < 0:
                    raise ImportProblem(f"{table}, строка {index}: {key} должно быть неотрицательным")
                row[key] = str(int(numeric)) if numeric.is_integer() else str(numeric)
            if key in DATES and value:
                try:
                    row[key] = date.fromisoformat(value).isoformat()
                except ValueError:
                    try:
                        row[key] = datetime.strptime(value, "%d.%m.%Y").date().isoformat()
                    except ValueError:
                        raise ImportProblem(f"{table}, строка {index}: дата должна быть YYYY-MM-DD или ДД.ММ.ГГГГ")
            if key == "active":
                row[key] = {"да": "true", "нет": "false", "1": "true", "0": "false"}.get(value.lower(), value.lower())
            if key == "customer_id" and ("@" in value or re.search(r"\+\d[\d ()-]{8,}", value)):
                raise ImportProblem(f"sales, строка {index}: вместо контактов нужен обезличенный ID")
        rows.append(row)
        if len(rows) > MAX_ROWS:
            raise ImportProblem("Слишком много строк в таблице", 413)
    return rows


def parse_file(filename, content):
    """Return normalized tables. Every sheet/row is validated, never skipped silently."""
    suffix = Path(filename).suffix.lower()
    tables = {}
    def add(name, matrix):
        key = table_name(name)
        if key in tables:
            raise ImportProblem(f"Повторная таблица {key}")
        tables[key] = normalize(key, matrix)
    try:
        if suffix in {".csv", ".tsv"}:
            try:
                text = content.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = content.decode("cp1251")
            delimiter = "\t" if suffix == ".tsv" else csv.Sniffer().sniff(text[:8192], delimiters=",;\t").delimiter
            matrix = list(csv.reader(StringIO(text), delimiter=delimiter))
            add(Path(filename).stem, matrix)
        elif suffix == ".json":
            value = json.loads(content)
            mapping = {Path(filename).stem: value} if isinstance(value, list) else value
            if not isinstance(mapping, dict):
                raise ImportProblem("JSON должен содержать таблицы или массив строк")
            for key, rows in mapping.items():
                name = table_name(key)
                if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
                    raise ImportProblem(f"{name}: ожидается массив объектов")
                headers = list(rows[0]) if rows else list(REQUIRED[name])
                if any(set(r) != set(headers) for r in rows):
                    raise ImportProblem(f"{name}: строки JSON имеют разные колонки")
                add(name, [headers] + [[r[h] for h in headers] for r in rows])
        elif suffix == ".xlsx":
            from openpyxl import load_workbook
            with zipfile.ZipFile(BytesIO(content)) as archive:
                if sum(i.file_size for i in archive.infolist()) > 60 * 1024 * 1024:
                    raise ImportProblem("Распакованная книга слишком велика", 413)
            workbook = load_workbook(BytesIO(content), read_only=True, data_only=False)
            try:
                for sheet in workbook:
                    if sheet.max_row > MAX_ROWS + 1 or sheet.max_column > 32:
                        raise ImportProblem("Слишком большой лист Excel", 413)
                    matrix = []
                    for row in sheet.iter_rows():
                        if any(c.data_type in {"f", "e"} for c in row):
                            raise ImportProblem(f"{sheet.title}: замените формулы/ошибки значениями")
                        matrix.append([c.value for c in row])
                    add(sheet.title, matrix)
            finally:
                workbook.close()
        elif suffix == ".xls":
            import xlrd
            workbook = xlrd.open_workbook(file_contents=content, on_demand=True)
            try:
                for sheet in workbook.sheets():
                    if sheet.nrows > MAX_ROWS + 1 or sheet.ncols > 32:
                        raise ImportProblem("Слишком большой лист Excel", 413)
                    matrix = []
                    for i in range(sheet.nrows):
                        values = []
                        for c in sheet.row(i):
                            if c.ctype == xlrd.XL_CELL_ERROR:
                                raise ImportProblem(f"{sheet.name}: ошибка в ячейке XLS")
                            values.append(xlrd.xldate.xldate_as_datetime(c.value, workbook.datemode)
                                          if c.ctype == xlrd.XL_CELL_DATE else c.value)
                        matrix.append(values)
                    add(sheet.name, matrix)
            finally:
                workbook.release_resources()
        elif suffix == ".pdf":
            import pdfplumber
            matrix = []
            with pdfplumber.open(BytesIO(content)) as pdf:
                if len(pdf.pages) > 50:
                    raise ImportProblem("PDF: максимум 50 страниц", 413)
                for page in pdf.pages:
                    if not (page.extract_text() or "").strip():
                        raise ImportProblem("PDF содержит скан/страницу без текста. Нужен OCR или выгрузка XLSX/CSV.")
                    extracted = page.extract_tables()
                    if not extracted:
                        raise ImportProblem("В PDF не найдены таблицы с границами. Экспортируйте XLSX/CSV.")
                    for table in extracted:
                        matrix.extend(table)
            add(Path(filename).stem, matrix)
        else:
            raise ImportProblem("Поддерживаются CSV, TSV, XLSX, XLS, JSON и текстовые PDF", 415)
    except ImportProblem:
        raise
    except Exception as error:
        raise ImportProblem(f"Не удалось прочитать {suffix} файл: проверьте формат, пароль и структуру таблицы") from error
    return tables


def select_warehouse(tables, selected):
    scoped = ("sales", "inventory", "material_statement", "stockouts", "in_transit")
    warehouses = {r.get("warehouse_id", "") for t in scoped for r in tables.get(t, []) if r.get("warehouse_id")}
    if len(warehouses) > 1 and not selected:
        raise ImportProblem("Обнаружено несколько складов. Укажите warehouse_id: " + ", ".join(sorted(warehouses)))
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


def import_dataset(files, data_root: Path, database_path: Path, *, anonymized: bool, warehouse_id=""):
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
            expanded_days += max(0, (date.fromisoformat(row["end_date"]) - date.fromisoformat(row["start_date"])).days + 1)
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
                    raise ImportProblem("Повторный артикул в остатках: требуется один конечный остаток")
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
            warnings.append(f"sales.{field}: есть пропуски; значения не придуманы, проверьте исходную выгрузку.")
    if not warehouse:
        warnings.append("Склад не указан: набор считается одним складом.")
    dataset = "upload_" + uuid4().hex
    data_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".import-", dir=data_root) as temp:
        folder = Path(temp)
        for name, headers in REQUIRED_FILES.items():
            fields = list(headers) + [f for f in OPTIONAL[name] if any(f in r for r in tables[name])]
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
            "dataset": dataset, "source": "1c_file_exchange" if "material_statement" in tables else "file_upload",
            "warehouse_id": warehouse, "counts": {key: len(value) for key, value in tables.items()},
            "warnings": warnings,
            "preview": {key: [{k: v for k, v in row.items() if k != "customer_id"} for row in value[:5]]
                        for key, value in tables.items()},
            "products": [{k: row.get(k, "") for k in ("sku", "name", "category", "unit")} for row in tables["products"]],
        }
        (folder / "manifest.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
        # Normalized snapshot includes supplied price/customer/warehouse fields.
        # Published IDs are random and paths never come from uploaded filenames.
        initialize_database(database_path)
        with connect(database_path) as db:
            db.execute("INSERT INTO source_imports(dataset, metadata_json, tables_json) VALUES (?, ?, ?)",
                       (dataset, json.dumps(metadata, ensure_ascii=False), json.dumps(tables, ensure_ascii=False)))
            destination = data_root / dataset
            folder.rename(destination)
    return metadata


def read_metadata(database_path, dataset):
    with connect(database_path) as db:
        row = db.execute("SELECT metadata_json FROM source_imports WHERE dataset=?", (dataset,)).fetchone()
    if row is None:
        raise ImportProblem("Набор не найден", 404)
    return json.loads(row["metadata_json"])
