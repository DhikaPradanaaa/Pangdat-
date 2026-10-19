from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from config import OLTP_DB, PROJECT_ROOT, RAW_SOURCE_DIR
from database import connect, engine, run_sql_file


FILES = {
    "category_translation": "product_category_name_translation.csv",
    "customers": "olist_customers_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "products": "olist_products_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
    "order_reviews": "olist_order_reviews_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
}

def bulk_load(cursor, table: str, path: Path, columns: list[str], filename: str) -> None:
    variables = [f"@v{i}" for i in range(len(columns))]
    assignments = [
        f"`{column}`=NULLIF(TRIM(BOTH '\\r' FROM {variable}),'')"
        for column, variable in zip(columns, variables)
    ]
    joined_values = ",".join(variables)
    assignments.extend(
        [
            f"source_file='{filename.replace(chr(39), chr(39) * 2)}'",
            f"source_row_hash=SHA2(CONCAT_WS('|',{joined_values}),256)",
        ]
    )
    safe_path = path.resolve().as_posix().replace("'", "''")
    sql = f"""
        LOAD DATA LOCAL INFILE '{safe_path}'
        INTO TABLE `{OLTP_DB}`.`{table}`
        CHARACTER SET utf8mb4
        FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"' ESCAPED BY '"'
        LINES TERMINATED BY '\\n'
        IGNORE 1 LINES
        ({','.join(variables)})
        SET {','.join(assignments)}
    """
    cursor.execute(sql)


def main() -> None:
    parser = argparse.ArgumentParser(description="Initial load CSV Olist ke OLTP MySQL Laragon.")
    parser.add_argument("--source-dir", type=Path, default=RAW_SOURCE_DIR)
    args = parser.parse_args()
    source_dir = args.source_dir.resolve()

    run_sql_file(PROJECT_ROOT / "sql" / "01_create_oltp.sql")
    ingestion_time = datetime.now(timezone.utc)
    counts: dict[str, int] = {}
    connection = connect()
    try:
        cursor = connection.cursor()
        cursor.execute("SET GLOBAL local_infile=1")
        cursor.execute("SET FOREIGN_KEY_CHECKS=0")
        for table, filename in FILES.items():
            path = source_dir / filename
            columns = list(pd.read_csv(path, nrows=0).columns)
            expected = sum(1 for _ in path.open("r", encoding="utf-8", errors="replace")) - 1
            # Review comments may contain embedded newlines; pandas gives the reliable logical row count.
            if table == "order_reviews":
                expected = len(pd.read_csv(path, low_memory=False))
            bulk_load(cursor, table, path, columns, filename)
            counts[table] = expected
        cursor.execute("SET FOREIGN_KEY_CHECKS=1")
        connection.commit()

        actual = {}
        for table, expected in counts.items():
            cursor.execute(f"SELECT COUNT(*) FROM `{OLTP_DB}`.`{table}`")
            actual[table] = cursor.fetchone()[0]
            if actual[table] == expected - 1:
                filename = FILES[table]
                first = pd.read_csv(source_dir / filename, nrows=1, low_memory=False)
                first["source_file"] = filename
                first["source_ingested_at"] = ingestion_time.replace(tzinfo=None)
                first["source_updated_at"] = ingestion_time.replace(tzinfo=None)
                raw_values = ["" if pd.isna(value) else str(value) for value in first.iloc[0, : len(first.columns) - 4]]
                first["source_row_hash"] = hashlib.sha256("|".join(raw_values).encode()).hexdigest()
                first.where(pd.notna(first), None).to_sql(
                    table, engine(OLTP_DB), if_exists="append", index=False
                )
                # End the current repeatable-read snapshot so this connection sees
                # the repair inserted through SQLAlchemy's separate connection.
                connection.commit()
                cursor.execute(f"SELECT COUNT(*) FROM `{OLTP_DB}`.`{table}`")
                actual[table] = cursor.fetchone()[0]
            if actual[table] != expected:
                raise RuntimeError(f"Rekonsiliasi {table} gagal: CSV={expected}, MySQL={actual[table]}")
    finally:
        connection.close()

    summary = {
        "loaded_at_utc": ingestion_time.isoformat(),
        "source_directory": str(source_dir),
        "database": OLTP_DB,
        "table_counts": actual,
        "total_rows": sum(actual.values()),
        "status": "SUCCESS",
    }
    output = PROJECT_ROOT / "runtime" / "seed_summary.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
