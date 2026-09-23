"""Explicit LOGISTIQ workbook adapter; reference answers never drive quantities."""

from datetime import date
from hashlib import sha256
import json
import math

from .normalization import ImportProblem, REQUIRED, cell, normalize

UPLOAD_COLUMNS = (
    "date warehouse sku product_name category supplier sales_qty lost_sales_estimate "
    "corrected_demand_qty stock_on_hand incoming_qty incoming_eta lead_time_days "
    "pack_size min_order_qty unit_cost_kzt service_level_target promo_flag "
    "stockout_flag anomaly_flag data_quality_note"
).split()
SNAPSHOT_COLUMNS = [
    "SKU",
    "Товар",
    "Категория",
    "Поставщик",
    "На складе",
    "В пути",
    "ETA",
    "Lead time",
    "Упаковка",
    "MOQ",
    "Backorders",
    "Service level",
    "Средний спрос 14д",
    "StdDev 14д",
    "Прогноз 30д",
    "Страховой запас",
    "Чистая потребность",
    "Рекомендация заказа",
    "Ожидаемый риск",
    "Сценарий",
    "Ожидаемое поведение",
]
WARNINGS = [
    "LOGISTIQ: текущие остатки и поставки взяты из Current Snapshot, а не из исторических строк.",
    "LOGISTIQ: Expected Results и контрольные прогнозы/заказы не используются. "
    "Аномалии и упущенный спрос рассчитываются заново по фактическим продажам.",
    "LOGISTIQ: MOQ, упаковки, backorders, service level и промо не меняют формулу MVP. "
    "Все товары в пути вычитаются без поправки на ETA. Результат может отличаться от Excel.",
    "LOGISTIQ: unit_cost_kzt — закупочная стоимость, не цена продажи; sales.price не заполнена.",
]


def _rows(matrix, columns, name):
    if len(matrix) < 4:
        raise ImportProblem(f"{name}: нужны заголовки в строке 3 и данные")
    headers = [cell(v) for v in matrix[2]]
    if len(headers) != len(set(headers)) or set(headers) != set(columns):
        raise ImportProblem(f"{name}: колонки строки 3 не соответствуют формату LOGISTIQ")
    rows = []
    for index, raw in enumerate(matrix[3:], 4):
        if not any(cell(v) for v in raw):
            continue
        if len(raw) != len(headers):
            raise ImportProblem(f"{name}, строка {index}: неверное число ячеек")
        row = {key: cell(value) for key, value in zip(headers, raw)}
        if any(len(value) > 1000 for value in row.values()):
            raise ImportProblem(f"{name}, строка {index}: слишком длинное значение")
        rows.append(row)
    if not rows:
        raise ImportProblem(f"{name}: нет данных")
    return rows


def _integer(value, field):
    try:
        number = float(value)
    except ValueError:
        raise ImportProblem(f"LOGISTIQ: {field} должно быть целым неотрицательным числом")
    if not math.isfinite(number) or number < 0 or not number.is_integer():
        raise ImportProblem(f"LOGISTIQ: {field} должно быть целым неотрицательным числом")
    return str(int(number))


def _date(value, field):
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise ImportProblem(f"LOGISTIQ: {field} должна быть датой YYYY-MM-DD")


def _supplier_id(name, lead_time):
    # A supplier-level lead time is mandated by the current contract.
    key = json.dumps([name, lead_time], ensure_ascii=False).encode("utf-8")
    return "LOG-" + sha256(key).hexdigest()[:24]


def parse_logistiq(workbook, read_sheet, warnings=None):
    expected = {"Upload Data", "Current Snapshot", "Expected Results", "Data Dictionary"}
    if set(workbook.sheetnames) != expected:
        raise ImportProblem(
            "LOGISTIQ: нужны четыре листа Upload Data, Current Snapshot, "
            "Expected Results, Data Dictionary без дополнительных листов"
        )
    history = _rows(read_sheet(workbook["Upload Data"]), UPLOAD_COLUMNS, "Upload Data")
    snapshot = _rows(read_sheet(workbook["Current Snapshot"]), SNAPSHOT_COLUMNS, "Current Snapshot")
    warehouses = {r["warehouse"] for r in history}
    if len(warehouses) != 1 or not next(iter(warehouses)):
        raise ImportProblem(
            "LOGISTIQ Current Snapshot не содержит склада: "
            "нужен ровно один заполненный склад в Upload Data"
        )
    warehouse = next(iter(warehouses))
    current = {}
    for row in snapshot:
        sku = row["SKU"]
        if not sku or sku in current:
            raise ImportProblem("Current Snapshot: пустой или повторяющийся SKU")
        current[sku] = row
    if set(current) != {r["sku"] for r in history}:
        raise ImportProblem("LOGISTIQ: наборы SKU в Upload Data и Current Snapshot различаются")
    tables = {key: [] for key in REQUIRED if key != "material_statement"}
    suppliers = {}
    terms = {}
    for sku, row in current.items():
        name = row["Поставщик"]
        if not name or not row["Товар"]:
            raise ImportProblem(f"Current Snapshot: заполните товар и поставщика для {sku}")
        lead = _integer(row["Lead time"], f"{sku} Lead time")
        supplier = _supplier_id(name, lead)
        terms.setdefault(name, set()).add(lead)
        suppliers[supplier] = dict(supplier_id=supplier, supplier_name=name, lead_time_days=lead)
        tables["products"].append(
            dict(
                sku=sku,
                name=row["Товар"],
                category=row["Категория"],
                supplier_id=supplier,
                active="true",
            )
        )
        tables["inventory"].append(
            dict(
                sku=sku,
                warehouse_id=warehouse,
                on_hand=_integer(row["На складе"], f"{sku} На складе"),
            )
        )
        quantity = _integer(row["В пути"], f"{sku} В пути")
        if row["ETA"]:
            _date(row["ETA"], f"{sku} ETA")
        if int(quantity):
            tables["in_transit"].append(
                dict(
                    sku=sku,
                    quantity=quantity,
                    warehouse_id=warehouse,
                    expected_date=_date(row["ETA"], f"{sku} ETA"),
                )
            )
    tables["suppliers"] = list(suppliers.values())
    seen = set()
    for row in history:
        sku = row["sku"]
        day = _date(row["date"], "date")
        if (sku, day) in seen:
            raise ImportProblem(f"Upload Data: повтор даты/SKU {day}, {sku}")
        seen.add((sku, day))
        source = current[sku]
        for field, snapshot_field in (
            ("product_name", "Товар"),
            ("category", "Категория"),
            ("supplier", "Поставщик"),
        ):
            if row[field] != source[snapshot_field]:
                raise ImportProblem(f"LOGISTIQ: {sku} {field} расходится между листами")
        for field in ("sales_qty", "stock_on_hand", "incoming_qty", "lead_time_days"):
            row[field] = _integer(row[field], f"{sku} {field}")
        if row["incoming_eta"] or int(row["incoming_qty"]):
            _date(row["incoming_eta"], f"{sku} incoming_eta")
        if row["stockout_flag"].lower() not in {"true", "false", "1", "0"}:
            raise ImportProblem(f"Upload Data: {sku} stockout_flag должен быть boolean")
        tables["sales"].append(
            dict(date=day, sku=sku, units=row["sales_qty"], warehouse_id=warehouse)
        )
        if row["stockout_flag"].lower() in {"true", "1"}:
            if int(row["stock_on_hand"]) or int(row["sales_qty"]):
                raise ImportProblem(f"Upload Data: {sku} stockout противоречит продажам/остаткам")
            tables["stockouts"].append(
                dict(sku=sku, start_date=day, end_date=day, warehouse_id=warehouse)
            )
    # Run the same cell/type checks as canonical uploads, then relational validation.
    for name, rows in tables.items():
        headers = list(rows[0]) if rows else list(REQUIRED[name])
        tables[name] = normalize(name, [headers] + [[r[h] for h in headers] for r in rows])
    if warnings is not None:
        warnings.extend(WARNINGS)
        if any(len(values) > 1 for values in terms.values()):
            warnings.append(
                "LOGISTIQ: один поставщик с разными сроками поставки разделён "
                "на группы по имени и lead time; названия сохранены."
            )
    return tables
