# Input CSV contract

Each dataset is a directory such as `data/demo/` containing the six files below. CSV files use UTF-8, a comma delimiter, one header row, `.` as decimal separator, and ISO dates (`YYYY-MM-DD`). Column names are exact and case-sensitive.

Imported optional columns customer_id, price, warehouse_id, category and unit are
retained in normalized source snapshots in SQLite. customer_id is used for
per-client/day outlier exclusion, warehouse_id scopes the dataset, category/unit
are returned as import metadata. Price is audit data, not a multiplier of unit demand.
The upload boundary rejects unknown columns; direct legacy CSV ignores unknown
columns. Missing required columns, duplicate master keys, invalid dates,
non-finite numbers, and negative quantities fail validation.

## `products.csv`

One row per SKU.

| Column | Type | Required | Rules |
|---|---|---:|---|
| `sku` | string | yes | Unique, non-empty. |
| `name` | string | yes | Non-empty display name. |
| `supplier_id` | string | yes | Must exist in `suppliers.csv`. |
| `active` | boolean | yes | `true` or `false`; only active products are calculated. |

Header:

```csv
sku,name,supplier_id,active
```

## `suppliers.csv`

One row per supplier.

| Column | Type | Required | Rules |
|---|---|---:|---|
| `supplier_id` | string | yes | Unique, non-empty. |
| `supplier_name` | string | yes | Non-empty display name. |
| `lead_time_days` | integer | yes | `>= 0`. |

Header:

```csv
supplier_id,supplier_name,lead_time_days
```

## `sales.csv`

Daily or transactional sales. With customer_id, the algorithm first excludes
one-off large client/day groups using a robust per-SKU threshold (at least eight
groups, threshold max(Q3 + 3 IQR, 5 median)). Repeated large groups for the same
client are retained at that stage. Daily detection then runs on cleaned totals.
Without customer_id, only daily detection is available, with an import warning.

| Column | Type | Required | Rules |
|---|---|---:|---|
| `date` | date | yes | ISO `YYYY-MM-DD`. |
| `sku` | string | yes | Must exist in `products.csv`. |
| `units` | number | yes | `>= 0`. |

Header:

```csv
date,sku,units
```

## `inventory.csv`

Current inventory snapshot, one row per active SKU.

| Column | Type | Required | Rules |
|---|---|---:|---|
| `sku` | string | yes | Unique; must exist in `products.csv`. |
| `on_hand` | integer | yes | `>= 0`. Negative values are data errors. |

Header:

```csv
sku,on_hand
```

## `in_transit.csv`

Open inbound quantity by SKU. Multiple rows per SKU are summed. The file and header are required, but a missing SKU is allowed and means zero with a warning reason.

| Column | Type | Required | Rules |
|---|---|---:|---|
| `sku` | string | yes | Must exist in `products.csv`. |
| `quantity` | integer | yes | `>= 0`. |
| `expected_date` | date | yes | ISO `YYYY-MM-DD`; informational in MVP. |

Header:

```csv
sku,quantity,expected_date
```

## `stockouts.csv`

Inclusive periods when the SKU could not satisfy demand. Overlapping or adjacent periods for one SKU are merged before compensation to avoid double counting.

| Column | Type | Required | Rules |
|---|---|---:|---|
| `sku` | string | yes | Must exist in `products.csv`. |
| `start_date` | date | yes | ISO `YYYY-MM-DD`. |
| `end_date` | date | yes | ISO `YYYY-MM-DD`; must be on or after `start_date`. |

Header:

```csv
sku,start_date,end_date
```

## Ownership and joins

```text
products.supplier_id -> suppliers.supplier_id
sales.sku             -> products.sku
inventory.sku         -> products.sku
in_transit.sku        -> products.sku
stockouts.sku         -> products.sku
```

An active product without inventory is an error. An active product without sales history is valid: demand and recommendation are zero, with an explanatory reason.
