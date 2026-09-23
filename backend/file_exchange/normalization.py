"""Canonical table names, headers, cell conversions and validation limits."""

from datetime import date, datetime
import math
import re
from agent.workflow.models import REQUIRED_FILES

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
    "продажи": "sales",
    "товары": "products",
    "поставщики": "suppliers",
    "остатки": "inventory",
    "отсутствие": "stockouts",
    "в пути": "in_transit",
    "материальная ведомость": "material_statement",
}
ALIASES = {
    "дата": "date",
    "артикул": "sku",
    "количество": "units",
    "обезличенный клиент": "customer_id",
    "цена": "price",
    "склад": "warehouse_id",
    "наименование": "name",
    "код поставщика": "supplier_id",
    "поставщик": "supplier_name",
    "срок поставки": "lead_time_days",
    "срок поставки дней": "lead_time_days",
    "остаток": "on_hand",
    "конечный остаток": "on_hand",
    "активен": "active",
    "дата начала": "start_date",
    "дата окончания": "end_date",
    "ожидаемая дата": "expected_date",
    "категория": "category",
    "единица": "unit",
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
        raise ImportProblem(
            f"{table}: неизвестные колонки {', '.join(sorted(unknown))}. Сверьте шаблон; не загружайте персональные данные."
        )
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
                    raise ImportProblem(
                        f"{table}, строка {index}: {key} должно быть неотрицательным"
                    )
                row[key] = str(int(numeric)) if numeric.is_integer() else str(numeric)
            if key in DATES and value:
                try:
                    row[key] = date.fromisoformat(value).isoformat()
                except ValueError:
                    try:
                        row[key] = datetime.strptime(value, "%d.%m.%Y").date().isoformat()
                    except ValueError:
                        raise ImportProblem(
                            f"{table}, строка {index}: дата должна быть YYYY-MM-DD или ДД.ММ.ГГГГ"
                        )
            if key == "active":
                row[key] = {"да": "true", "нет": "false", "1": "true", "0": "false"}.get(
                    value.lower(), value.lower()
                )
            if key == "customer_id" and ("@" in value or re.search(r"\+\d[\d ()-]{8,}", value)):
                raise ImportProblem(
                    f"sales, строка {index}: вместо контактов нужен обезличенный ID"
                )
        rows.append(row)
        if len(rows) > MAX_ROWS:
            raise ImportProblem("Слишком много строк в таблице", 413)
    return rows
