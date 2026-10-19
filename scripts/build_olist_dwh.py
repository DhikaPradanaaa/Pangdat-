from __future__ import annotations

import argparse
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


SOURCE_FILES = {
    "customers": "olist_customers_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "items": "olist_order_items_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "categories": "product_category_name_translation.csv",
}

ID_DTYPES = {
    "customer_id": "string",
    "customer_unique_id": "string",
    "customer_zip_code_prefix": "string",
    "seller_id": "string",
    "seller_zip_code_prefix": "string",
    "geolocation_zip_code_prefix": "string",
    "order_id": "string",
    "product_id": "string",
    "review_id": "string",
    "review_key": "string",
    "product_category_name": "string",
    "product_category_name_english": "string",
    "dq_status": "string",
    "dq_issue_codes": "string",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_sources(source_dir: Path) -> dict[str, pd.DataFrame]:
    missing = [name for name in SOURCE_FILES.values() if not (source_dir / name).exists()]
    if missing:
        raise FileNotFoundError(f"File sumber tidak ditemukan: {', '.join(missing)}")

    frames: dict[str, pd.DataFrame] = {}
    for alias, filename in SOURCE_FILES.items():
        header = pd.read_csv(source_dir / filename, nrows=0).columns
        dtypes = {name: dtype for name, dtype in ID_DTYPES.items() if name in header}
        frames[alias] = pd.read_csv(source_dir / filename, dtype=dtypes, low_memory=False)
    return frames


def eligible(df: pd.DataFrame, include_errors: bool) -> pd.DataFrame:
    if include_errors or "dq_status" not in df.columns:
        return df.copy()
    return df.loc[df["dq_status"].ne("error")].copy()


def clean_text(series: pd.Series) -> pd.Series:
    return series.astype("string").fillna("")


def parse_datetime(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce")


def date_key(series: pd.Series) -> pd.Series:
    parsed = parse_datetime(series)
    return pd.to_numeric(parsed.dt.strftime("%Y%m%d"), errors="coerce").fillna(0).astype("int64")


def elapsed_hours(end: pd.Series, start: pd.Series) -> pd.Series:
    result = (parse_datetime(end) - parse_datetime(start)).dt.total_seconds() / 3600.0
    return result.round(4)


def add_unknown_row(df: pd.DataFrame, row: dict) -> pd.DataFrame:
    return pd.concat([pd.DataFrame([row]), df], ignore_index=True)


def append_rejects(
    rejects: list[dict],
    run_id: str,
    source_table: str,
    frame: pd.DataFrame,
    key_columns: list[str],
    reason: str,
) -> None:
    for row in frame.itertuples(index=False):
        values = row._asdict()
        business_key = "|".join(str(values.get(col, "")) for col in key_columns)
        rejects.append(
            {
                "run_id": run_id,
                "source_table": source_table,
                "business_key": business_key,
                "rejection_reason": reason,
                "dq_status": values.get("dq_status", ""),
                "dq_issue_codes": values.get("dq_issue_codes", ""),
            }
        )


def build_date_dimension(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    candidates = [
        frames["orders"]["order_purchase_timestamp"],
        frames["orders"]["order_approved_at"],
        frames["orders"]["order_delivered_carrier_date"],
        frames["orders"]["order_delivered_customer_date"],
        frames["orders"]["order_estimated_delivery_date"],
        frames["items"]["shipping_limit_date"],
        frames["reviews"]["review_creation_date"],
        frames["reviews"]["review_answer_timestamp"],
    ]
    dates = pd.concat([parse_datetime(s).dt.normalize() for s in candidates], ignore_index=True)
    dates = pd.Series(dates.dropna().unique()).sort_values().reset_index(drop=True)

    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    month_names = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]
    iso = dates.dt.isocalendar()
    result = pd.DataFrame(
        {
            "date_key": dates.dt.strftime("%Y%m%d").astype("int64"),
            "full_date": dates.dt.strftime("%Y-%m-%d"),
            "day_of_month": dates.dt.day.astype("int64"),
            "day_name": dates.dt.dayofweek.map(dict(enumerate(day_names))),
            "day_of_week": (dates.dt.dayofweek + 1).astype("int64"),
            "week_of_year": iso.week.astype("int64"),
            "month_number": dates.dt.month.astype("int64"),
            "month_name": dates.dt.month.map({i + 1: name for i, name in enumerate(month_names)}),
            "quarter_number": dates.dt.quarter.astype("int64"),
            "year_number": dates.dt.year.astype("int64"),
            "is_weekend": dates.dt.dayofweek.isin([5, 6]).astype("int64"),
        }
    )
    unknown = {
        "date_key": 0,
        "full_date": None,
        "day_of_month": None,
        "day_name": "Unknown",
        "day_of_week": None,
        "week_of_year": None,
        "month_number": None,
        "month_name": "Unknown",
        "quarter_number": None,
        "year_number": None,
        "is_weekend": 0,
    }
    return add_unknown_row(result, unknown)


def build_dimensions(
    frames: dict[str, pd.DataFrame], include_errors: bool
) -> tuple[dict[str, pd.DataFrame], dict[str, dict[str, int]]]:
    geo = eligible(frames["geolocation"], include_errors).sort_values("geolocation_zip_code_prefix").reset_index(drop=True)
    geo["geolocation_key"] = np.arange(1, len(geo) + 1, dtype=np.int64)
    dim_geo = pd.DataFrame(
        {
            "geolocation_key": geo["geolocation_key"],
            "zip_code_prefix": clean_text(geo["geolocation_zip_code_prefix"]),
            "city": geo["geolocation_city"],
            "state": geo["geolocation_state"],
            "latitude": pd.to_numeric(geo["geolocation_lat"], errors="coerce"),
            "longitude": pd.to_numeric(geo["geolocation_lng"], errors="coerce"),
            "valid_coordinate_count": pd.to_numeric(geo["valid_coordinate_count"], errors="coerce"),
            "source_point_count": pd.to_numeric(geo["source_point_count"], errors="coerce"),
            "source_city_state_count": pd.to_numeric(geo["source_city_state_count"], errors="coerce"),
            "conflict_flag": geo["geolocation_conflict_flag"].astype(bool).astype("int64"),
            "dq_status": geo["dq_status"],
            "dq_issue_codes": geo["dq_issue_codes"],
        }
    )
    dim_geo = add_unknown_row(
        dim_geo,
        {
            "geolocation_key": 0,
            "zip_code_prefix": "__UNKNOWN__",
            "city": "unknown",
            "state": None,
            "latitude": None,
            "longitude": None,
            "valid_coordinate_count": 0,
            "source_point_count": 0,
            "source_city_state_count": 0,
            "conflict_flag": 0,
            "dq_status": "system",
            "dq_issue_codes": "UNKNOWN_MEMBER",
        },
    )
    geo_map = dict(zip(dim_geo["zip_code_prefix"], dim_geo["geolocation_key"]))

    categories = frames["categories"].drop_duplicates("product_category_name", keep="last")
    category_en = dict(zip(categories["product_category_name"], categories["product_category_name_english"]))
    category_status = dict(zip(categories["product_category_name"], categories["translation_status"]))

    products = eligible(frames["products"], include_errors).sort_values("product_id").reset_index(drop=True)
    products["product_key"] = np.arange(1, len(products) + 1, dtype=np.int64)
    dim_product = pd.DataFrame(
        {
            "product_key": products["product_key"],
            "product_id": products["product_id"],
            "category_name": products["product_category_name"],
            "category_name_english": products["product_category_name"].map(category_en),
            "translation_status": products["product_category_name"].map(category_status).fillna("unmapped"),
            "product_name_length": products["product_name_length"],
            "product_description_length": products["product_description_length"],
            "product_photos_qty": products["product_photos_qty"],
            "product_weight_g": products["product_weight_g"],
            "product_length_cm": products["product_length_cm"],
            "product_height_cm": products["product_height_cm"],
            "product_width_cm": products["product_width_cm"],
            "dq_status": products["dq_status"],
            "dq_issue_codes": products["dq_issue_codes"],
        }
    )
    dim_product = add_unknown_row(
        dim_product,
        {
            "product_key": 0,
            "product_id": "__UNKNOWN__",
            "category_name": "unknown",
            "category_name_english": "unknown",
            "translation_status": "system",
            "dq_status": "system",
            "dq_issue_codes": "UNKNOWN_MEMBER",
        },
    )

    customers = eligible(frames["customers"], include_errors).sort_values("customer_id").reset_index(drop=True)
    customers["customer_key"] = np.arange(1, len(customers) + 1, dtype=np.int64)
    customer_zip = clean_text(customers["customer_zip_code_prefix"])
    dim_customer = pd.DataFrame(
        {
            "customer_key": customers["customer_key"],
            "customer_id": customers["customer_id"],
            "customer_unique_id": customers["customer_unique_id"],
            "zip_code_prefix": customer_zip,
            "geolocation_key": customer_zip.map(geo_map).fillna(0).astype("int64"),
            "city": customers["customer_city_canonical"].fillna(customers["customer_city"]),
            "state": customers["customer_state_canonical"].fillna(customers["customer_state"]),
            "dq_status": customers["dq_status"],
            "dq_issue_codes": customers["dq_issue_codes"],
        }
    )
    dim_customer = add_unknown_row(
        dim_customer,
        {
            "customer_key": 0,
            "customer_id": "__UNKNOWN__",
            "customer_unique_id": "__UNKNOWN__",
            "zip_code_prefix": None,
            "geolocation_key": 0,
            "city": "unknown",
            "state": None,
            "dq_status": "system",
            "dq_issue_codes": "UNKNOWN_MEMBER",
        },
    )

    sellers = eligible(frames["sellers"], include_errors).sort_values("seller_id").reset_index(drop=True)
    sellers["seller_key"] = np.arange(1, len(sellers) + 1, dtype=np.int64)
    seller_zip = clean_text(sellers["seller_zip_code_prefix"])
    dim_seller = pd.DataFrame(
        {
            "seller_key": sellers["seller_key"],
            "seller_id": sellers["seller_id"],
            "zip_code_prefix": seller_zip,
            "geolocation_key": seller_zip.map(geo_map).fillna(0).astype("int64"),
            "city": sellers["seller_city_canonical"].fillna(sellers["seller_city"]),
            "state": sellers["seller_state_canonical"].fillna(sellers["seller_state"]),
            "dq_status": sellers["dq_status"],
            "dq_issue_codes": sellers["dq_issue_codes"],
        }
    )
    dim_seller = add_unknown_row(
        dim_seller,
        {
            "seller_key": 0,
            "seller_id": "__UNKNOWN__",
            "zip_code_prefix": None,
            "geolocation_key": 0,
            "city": "unknown",
            "state": None,
            "dq_status": "system",
            "dq_issue_codes": "UNKNOWN_MEMBER",
        },
    )

    mappings = {
        "geolocation": geo_map,
        "product": dict(zip(dim_product["product_id"], dim_product["product_key"])),
        "customer": dict(zip(dim_customer["customer_id"], dim_customer["customer_key"])),
        "seller": dict(zip(dim_seller["seller_id"], dim_seller["seller_key"])),
    }
    dimensions = {
        "dim_date": build_date_dimension(frames),
        "dim_geolocation": dim_geo,
        "dim_customer": dim_customer,
        "dim_seller": dim_seller,
        "dim_product": dim_product,
    }
    return dimensions, mappings


def build_facts(
    frames: dict[str, pd.DataFrame],
    mappings: dict[str, dict[str, int]],
    include_errors: bool,
    run_id: str,
    rejects: list[dict],
) -> dict[str, pd.DataFrame]:
    orders_all = frames["orders"]
    if not include_errors:
        append_rejects(
            rejects,
            run_id,
            SOURCE_FILES["orders"],
            orders_all.loc[orders_all["dq_status"].eq("error")],
            ["order_id"],
            "dq_status=error",
        )
    orders = eligible(orders_all, include_errors).sort_values("order_id").reset_index(drop=True)
    orders["order_key"] = np.arange(1, len(orders) + 1, dtype=np.int64)
    order_map = dict(zip(orders["order_id"], orders["order_key"]))
    purchase_date_map = dict(zip(orders["order_id"], date_key(orders["order_purchase_timestamp"])))

    delivered = parse_datetime(orders["order_delivered_customer_date"])
    estimated = parse_datetime(orders["order_estimated_delivery_date"])
    fact_order = pd.DataFrame(
        {
            "order_key": orders["order_key"],
            "order_id": orders["order_id"],
            "customer_key": orders["customer_id"].map(mappings["customer"]).fillna(0).astype("int64"),
            "purchase_date_key": date_key(orders["order_purchase_timestamp"]),
            "approved_date_key": date_key(orders["order_approved_at"]),
            "carrier_date_key": date_key(orders["order_delivered_carrier_date"]),
            "delivered_date_key": date_key(orders["order_delivered_customer_date"]),
            "estimated_delivery_date_key": date_key(orders["order_estimated_delivery_date"]),
            "order_status": orders["order_status"],
            "purchase_timestamp": orders["order_purchase_timestamp"],
            "approved_timestamp": orders["order_approved_at"],
            "carrier_timestamp": orders["order_delivered_carrier_date"],
            "delivered_timestamp": orders["order_delivered_customer_date"],
            "estimated_delivery_timestamp": orders["order_estimated_delivery_date"],
            "calculated_order_total": orders["calculated_order_total"],
            "recorded_payment_total": orders["recorded_payment_total"],
            "payment_difference": orders["payment_difference"],
            "approval_hours": elapsed_hours(orders["order_approved_at"], orders["order_purchase_timestamp"]),
            "carrier_lead_hours": elapsed_hours(orders["order_delivered_carrier_date"], orders["order_approved_at"]),
            "delivery_days": (elapsed_hours(orders["order_delivered_customer_date"], orders["order_purchase_timestamp"]) / 24).round(4),
            "delay_days": ((delivered - estimated).dt.total_seconds() / 86400.0).round(4),
            "is_delivered": delivered.notna().astype("int64"),
            "is_late": (delivered.notna() & estimated.notna() & delivered.gt(estimated)).astype("int64"),
            "dq_status": orders["dq_status"],
            "dq_issue_codes": orders["dq_issue_codes"],
        }
    )

    def child_rows(alias: str, key_columns: list[str]) -> pd.DataFrame:
        source = frames[alias]
        own_error = source["dq_status"].eq("error") if "dq_status" in source else pd.Series(False, index=source.index)
        missing_parent = ~source["order_id"].isin(order_map)
        if not include_errors:
            append_rejects(
                rejects,
                run_id,
                SOURCE_FILES[alias],
                source.loc[own_error],
                key_columns,
                "dq_status=error",
            )
            append_rejects(
                rejects,
                run_id,
                SOURCE_FILES[alias],
                source.loc[~own_error & missing_parent],
                key_columns,
                "parent order ditolak",
            )
            return source.loc[~own_error & ~missing_parent].copy()
        return source.loc[~missing_parent].copy()

    items = child_rows("items", ["order_id", "order_item_id"]).sort_values(["order_id", "order_item_id"]).reset_index(drop=True)
    fact_sales = pd.DataFrame(
        {
            "sales_key": np.arange(1, len(items) + 1, dtype=np.int64),
            "order_key": items["order_id"].map(order_map).astype("int64"),
            "order_id": items["order_id"],
            "order_item_id": pd.to_numeric(items["order_item_id"], errors="raise").astype("int64"),
            "product_key": items["product_id"].map(mappings["product"]).fillna(0).astype("int64"),
            "seller_key": items["seller_id"].map(mappings["seller"]).fillna(0).astype("int64"),
            "purchase_date_key": items["order_id"].map(purchase_date_map).astype("int64"),
            "shipping_limit_date_key": date_key(items["shipping_limit_date"]),
            "shipping_limit_timestamp": items["shipping_limit_date"],
            "price": pd.to_numeric(items["price"], errors="raise"),
            "freight_value": pd.to_numeric(items["freight_value"], errors="raise"),
            "line_total": pd.to_numeric(items["line_total"], errors="raise"),
            "dq_status": items["dq_status"],
            "dq_issue_codes": items["dq_issue_codes"],
        }
    )

    payments = child_rows("payments", ["order_id", "payment_sequential"]).sort_values(["order_id", "payment_sequential"]).reset_index(drop=True)
    fact_payment = pd.DataFrame(
        {
            "payment_key": np.arange(1, len(payments) + 1, dtype=np.int64),
            "order_key": payments["order_id"].map(order_map).astype("int64"),
            "order_id": payments["order_id"],
            "payment_sequential": pd.to_numeric(payments["payment_sequential"], errors="raise").astype("int64"),
            "purchase_date_key": payments["order_id"].map(purchase_date_map).astype("int64"),
            "payment_type": payments["payment_type"],
            "payment_installments": pd.to_numeric(payments["payment_installments"], errors="raise").astype("int64"),
            "payment_value": pd.to_numeric(payments["payment_value"], errors="raise"),
            "dq_status": payments["dq_status"],
            "dq_issue_codes": payments["dq_issue_codes"],
        }
    )

    reviews = child_rows("reviews", ["review_key"]).sort_values("review_key").reset_index(drop=True)
    fact_review = pd.DataFrame(
        {
            "review_key": np.arange(1, len(reviews) + 1, dtype=np.int64),
            "review_business_key": reviews["review_key"],
            "review_id": reviews["review_id"],
            "order_key": reviews["order_id"].map(order_map).astype("int64"),
            "order_id": reviews["order_id"],
            "creation_date_key": date_key(reviews["review_creation_date"]),
            "answer_date_key": date_key(reviews["review_answer_timestamp"]),
            "review_score": pd.to_numeric(reviews["review_score"], errors="raise").astype("int64"),
            "review_comment_title": reviews["review_comment_title"],
            "review_comment_message": reviews["review_comment_message"],
            "creation_timestamp": reviews["review_creation_date"],
            "answer_timestamp": reviews["review_answer_timestamp"],
            "response_hours": elapsed_hours(reviews["review_answer_timestamp"], reviews["review_creation_date"]),
            "dq_status": reviews["dq_status"],
            "dq_issue_codes": reviews["dq_issue_codes"],
        }
    )

    mappings["order"] = order_map
    return {
        "fact_order": fact_order,
        "fact_sales": fact_sales,
        "fact_payment": fact_payment,
        "fact_review": fact_review,
    }


def insert_frame(connection: sqlite3.Connection, table: str, frame: pd.DataFrame) -> None:
    frame.to_sql(table, connection, if_exists="append", index=False, chunksize=5000)


def scalar_query(connection: sqlite3.Connection, query: str) -> object:
    return connection.execute(query).fetchone()[0]


def validate(
    connection: sqlite3.Connection,
    run_id: str,
    frames: dict[str, pd.DataFrame],
    dimensions: dict[str, pd.DataFrame],
    facts: dict[str, pd.DataFrame],
    include_errors: bool,
) -> list[dict]:
    results: list[dict] = []

    def check(name: str, expected: object, actual: object, detail: str = "", tolerance: float | None = None) -> None:
        if tolerance is None:
            passed = expected == actual
        else:
            passed = abs(float(expected) - float(actual)) <= tolerance
        results.append(
            {
                "run_id": run_id,
                "check_name": name,
                "status": "PASS" if passed else "FAIL",
                "expected_value": str(expected),
                "actual_value": str(actual),
                "detail": detail,
            }
        )

    fk_violations = len(connection.execute("PRAGMA foreign_key_check").fetchall())
    check("foreign_key_violations", 0, fk_violations)

    for table, frame in dimensions.items():
        check(f"row_count_{table}", len(frame), scalar_query(connection, f"SELECT COUNT(*) FROM {table}"))
    for table, frame in facts.items():
        check(f"row_count_{table}", len(frame), scalar_query(connection, f"SELECT COUNT(*) FROM {table}"))

    uniqueness = {
        "dim_geolocation_zip": "SELECT COUNT(*) - COUNT(DISTINCT zip_code_prefix) FROM dim_geolocation",
        "dim_customer_id": "SELECT COUNT(*) - COUNT(DISTINCT customer_id) FROM dim_customer",
        "dim_seller_id": "SELECT COUNT(*) - COUNT(DISTINCT seller_id) FROM dim_seller",
        "dim_product_id": "SELECT COUNT(*) - COUNT(DISTINCT product_id) FROM dim_product",
        "fact_order_id": "SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM fact_order",
        "fact_sales_grain": "SELECT COUNT(*) - COUNT(DISTINCT order_id || ':' || order_item_id) FROM fact_sales",
        "fact_payment_grain": "SELECT COUNT(*) - COUNT(DISTINCT order_id || ':' || payment_sequential) FROM fact_payment",
        "fact_review_business_key": "SELECT COUNT(*) - COUNT(DISTINCT review_business_key) FROM fact_review",
    }
    for name, query in uniqueness.items():
        check(name, 0, scalar_query(connection, query))

    source_sales = round(float(facts["fact_sales"]["line_total"].sum()), 2)
    dwh_sales = round(float(scalar_query(connection, "SELECT COALESCE(SUM(line_total), 0) FROM fact_sales")), 2)
    check("sales_total_reconciliation", source_sales, dwh_sales, tolerance=0.01)

    source_payments = round(float(facts["fact_payment"]["payment_value"].sum()), 2)
    dwh_payments = round(float(scalar_query(connection, "SELECT COALESCE(SUM(payment_value), 0) FROM fact_payment")), 2)
    check("payment_total_reconciliation", source_payments, dwh_payments, tolerance=0.01)

    source_order_total = round(float(facts["fact_order"]["calculated_order_total"].fillna(0).sum()), 2)
    dwh_order_total = round(float(scalar_query(connection, "SELECT COALESCE(SUM(calculated_order_total), 0) FROM fact_order")), 2)
    check("order_total_reconciliation", source_order_total, dwh_order_total, tolerance=0.01)

    if not include_errors:
        for table in facts:
            check(
                f"no_error_rows_{table}",
                0,
                scalar_query(connection, f"SELECT COUNT(*) FROM {table} WHERE dq_status = 'error'"),
            )

    expected_orders = len(eligible(frames["orders"], include_errors))
    check("eligible_orders_loaded", expected_orders, len(facts["fact_order"]))
    return results


def write_documentation(output_dir: Path, counts: dict[str, int], validation: list[dict]) -> None:
    status_counts = pd.Series([row["status"] for row in validation]).value_counts().to_dict()
    readme = f"""# Olist Data Warehouse

Data warehouse ini dibangun dari CSV berkualitas pada `olist_data_quality_final/clean` dengan metode full refresh.

## Model

- `dim_date`: kalender untuk seluruh tanggal transaksi.
- `dim_geolocation`: satu anggota per prefix kode pos kanonis.
- `dim_customer`: grain satu `customer_id`; `customer_unique_id` tetap tersedia untuk analisis pelanggan lintas pesanan.
- `dim_seller`: grain satu penjual.
- `dim_product`: grain satu produk, termasuk kategori Portugis dan terjemahan Inggris.
- `fact_order`: grain satu pesanan.
- `fact_sales`: grain satu item dalam pesanan.
- `fact_payment`: grain satu urutan pembayaran dalam pesanan.
- `fact_review`: grain satu `review_key` komposit.

Fakta pembayaran dan ulasan sengaja dipisahkan dari item penjualan. Jangan menggabungkan ketiganya langsung tanpa agregasi per pesanan karena dapat menggandakan nilai. Gunakan `vw_order_summary` untuk analisis gabungan yang aman.

## Kebijakan kualitas

Secara default, baris `dq_status=error` tidak dimuat ke fakta/dimensi utama. Baris tersebut dan baris anak yang kehilangan parent dicatat di `etl_reject`. Baris `valid`, `corrected`, dan `warning` tetap dimuat beserta `dq_status` dan `dq_issue_codes`.

## Menjalankan ulang

```powershell
python D:\\Pangdat\\scripts\\build_olist_dwh.py
```

Gunakan `--include-errors` hanya bila analisis memerlukan seluruh baris sumber dan konsekuensi kualitasnya telah diterima.

## Hasil muat

{chr(10).join(f'- `{name}`: {count:,} baris' for name, count in counts.items())}

Validasi: {status_counts.get('PASS', 0)} PASS dan {status_counts.get('FAIL', 0)} FAIL.
"""
    (output_dir / "README.md").write_text(readme, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bangun Olist star-schema data warehouse di SQLite.")
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=Path(r"D:\Pangdat\output\olist_data_quality_final\clean"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(r"D:\Pangdat\output\olist_dwh"),
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path(r"D:\Pangdat\dwh\schema.sql"),
    )
    parser.add_argument("--include-errors", action="store_true")
    args = parser.parse_args()

    source_dir = args.source_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    database_path = output_dir / "olist_dwh.sqlite"
    temporary_path = output_dir / "olist_dwh.building.sqlite"
    if temporary_path.exists():
        temporary_path.unlink()

    run_id = str(uuid.uuid4())
    started_at = utc_now()
    frames = read_sources(source_dir)
    source_count = sum(len(frame) for frame in frames.values())
    rejects: list[dict] = []

    if not args.include_errors:
        geo_errors = frames["geolocation"].loc[frames["geolocation"]["dq_status"].eq("error")]
        append_rejects(
            rejects,
            run_id,
            SOURCE_FILES["geolocation"],
            geo_errors,
            ["geolocation_zip_code_prefix"],
            "dq_status=error",
        )

    dimensions, mappings = build_dimensions(frames, args.include_errors)
    facts = build_facts(frames, mappings, args.include_errors, run_id, rejects)

    connection = sqlite3.connect(temporary_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = OFF")
        connection.execute("PRAGMA synchronous = OFF")
        connection.executescript(args.schema.read_text(encoding="utf-8"))
        connection.execute(
            """
            INSERT INTO etl_run (
                run_id, started_at_utc, status, source_directory,
                include_error_rows, source_row_count, loaded_row_count,
                rejected_row_count, notes
            ) VALUES (?, ?, 'RUNNING', ?, ?, ?, NULL, ?, ?)
            """,
            (
                run_id,
                started_at,
                str(source_dir),
                int(args.include_errors),
                source_count,
                len(rejects),
                "Full refresh dari dataset hasil data-quality pipeline.",
            ),
        )
        for table, frame in dimensions.items():
            insert_frame(connection, table, frame)
        for table, frame in facts.items():
            insert_frame(connection, table, frame)
        if rejects:
            insert_frame(connection, "etl_reject", pd.DataFrame(rejects))

        validation = validate(connection, run_id, frames, dimensions, facts, args.include_errors)
        insert_frame(connection, "etl_validation_result", pd.DataFrame(validation))
        loaded_count = sum(len(frame) for frame in dimensions.values()) + sum(len(frame) for frame in facts.values())
        fail_count = sum(row["status"] == "FAIL" for row in validation)
        connection.execute(
            """
            UPDATE etl_run
            SET completed_at_utc = ?, status = ?, loaded_row_count = ?, rejected_row_count = ?
            WHERE run_id = ?
            """,
            (utc_now(), "SUCCESS" if fail_count == 0 else "FAILED_VALIDATION", loaded_count, len(rejects), run_id),
        )
        connection.commit()
    finally:
        connection.close()

    validation_path = output_dir / "validation_report.csv"
    pd.DataFrame(validation).to_csv(validation_path, index=False)
    summary = {
        "run_id": run_id,
        "started_at_utc": started_at,
        "completed_at_utc": utc_now(),
        "source_directory": str(source_dir),
        "database": str(database_path),
        "include_error_rows": args.include_errors,
        "source_row_count": source_count,
        "loaded_table_counts": {
            **{table: len(frame) for table, frame in dimensions.items()},
            **{table: len(frame) for table, frame in facts.items()},
        },
        "rejected_row_count": len(rejects),
        "validation_pass_count": sum(row["status"] == "PASS" for row in validation),
        "validation_fail_count": sum(row["status"] == "FAIL" for row in validation),
    }
    (output_dir / "etl_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_documentation(output_dir, summary["loaded_table_counts"], validation)

    if summary["validation_fail_count"]:
        raise RuntimeError(
            f"ETL menghasilkan {summary['validation_fail_count']} pemeriksaan gagal. "
            f"Database sementara dipertahankan di {temporary_path}."
        )

    if database_path.exists():
        database_path.unlink()
    temporary_path.replace(database_path)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
