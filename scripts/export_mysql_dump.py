from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
from pathlib import Path


TABLES = [
    "etl_run",
    "dim_date",
    "dim_geolocation",
    "dim_customer",
    "dim_seller",
    "dim_product",
    "fact_order",
    "fact_sales",
    "fact_payment",
    "fact_review",
    "etl_reject",
    "etl_validation_result",
]


def mysql_literal(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return "NULL"
        return repr(value)
    if isinstance(value, bytes):
        return "0x" + value.hex()

    text = str(value)
    text = (
        text.replace("\\", "\\\\")
        .replace("\x00", "\\0")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
        .replace("\x1a", "\\Z")
        .replace("'", "\\'")
    )
    return f"'{text}'"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_table(
    connection: sqlite3.Connection,
    output,
    table: str,
    batch_size: int,
) -> int:
    columns = [row[1] for row in connection.execute(f"PRAGMA table_info(`{table}`)")]
    if not columns:
        raise ValueError(f"Tabel SQLite tidak ditemukan: {table}")
    quoted_columns = ", ".join(f"`{column}`" for column in columns)
    cursor = connection.execute(f"SELECT {quoted_columns} FROM `{table}`")
    row_count = 0
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
        values = []
        for row in rows:
            values.append("(" + ",".join(mysql_literal(value) for value in row) + ")")
        output.write(f"INSERT INTO `{table}` ({quoted_columns}) VALUES\n")
        output.write(",\n".join(values))
        output.write(";\n")
        row_count += len(rows)
    return row_count


def main() -> None:
    workspace_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Ekspor Olist DWH SQLite menjadi dump MySQL 8.")
    parser.add_argument(
        "--sqlite-db",
        type=Path,
        default=workspace_root / "output" / "olist_dwh" / "olist_dwh.sqlite",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=workspace_root / "mysql" / "schema_mysql.sql",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=workspace_root / "output" / "olist_dwh_mysql" / "olist_dwh_mysql.sql",
    )
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()

    sqlite_db = args.sqlite_db.resolve()
    schema_path = args.schema.resolve()
    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(sqlite_db)
    counts: dict[str, int] = {}
    try:
        with output_path.open("w", encoding="utf-8", newline="\n") as output:
            output.write("-- Olist Data Warehouse - MySQL 8 full dump\n")
            output.write("-- Dibangun dari dataset yang sudah melalui data-quality pipeline.\n\n")
            output.write(schema_path.read_text(encoding="utf-8"))
            output.write("\n\nSET FOREIGN_KEY_CHECKS = 0;\n")
            output.write("SET UNIQUE_CHECKS = 0;\n")
            output.write("SET AUTOCOMMIT = 0;\n")
            output.write("START TRANSACTION;\n\n")
            for table in TABLES:
                output.write(f"-- Data `{table}`\n")
                counts[table] = export_table(connection, output, table, args.batch_size)
                output.write("\n")
            output.write("COMMIT;\n")
            output.write("SET AUTOCOMMIT = 1;\n")
            output.write("SET UNIQUE_CHECKS = 1;\n")
            output.write("SET FOREIGN_KEY_CHECKS = 1;\n")
    finally:
        connection.close()

    summary = {
        "source_sqlite": str(sqlite_db),
        "mysql_dump": str(output_path),
        "mysql_version": "8.0+",
        "database_name": "olist_dwh",
        "table_counts": counts,
        "dump_size_bytes": output_path.stat().st_size,
        "dump_sha256": sha256(output_path),
    }
    summary_path = output_path.parent / "mysql_export_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
