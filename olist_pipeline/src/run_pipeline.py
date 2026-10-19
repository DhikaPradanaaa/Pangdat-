from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import uuid
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from config import (
    DWH_DB,
    LOG_DIR,
    MYSQL_CLIENT,
    MYSQL_EXPORT_SCRIPT,
    MYSQL_HOST,
    MYSQL_PASSWORD,
    MYSQL_PORT,
    MYSQL_SCHEMA,
    MYSQL_USER,
    OLTP_DB,
    PROJECT_ROOT,
    QUALITY_SCRIPT,
    RUNTIME_DIR,
    SQLITE_DWH_SCRIPT,
    SQLITE_SCHEMA,
    STAGING_DB,
)
from database import connect, engine, run_sql_file


PIPELINE_NAME = "olist_daily_etl"

SOURCE_TABLES = {
    "customers": ("olist_customers_dataset.csv", [
        "customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state"
    ]),
    "sellers": ("olist_sellers_dataset.csv", [
        "seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"
    ]),
    "category_translation": ("product_category_name_translation.csv", [
        "product_category_name", "product_category_name_english"
    ]),
    "products": ("olist_products_dataset.csv", [
        "product_id", "product_category_name", "product_name_lenght", "product_description_lenght",
        "product_photos_qty", "product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"
    ]),
    "orders": ("olist_orders_dataset.csv", [
        "order_id", "customer_id", "order_status", "order_purchase_timestamp", "order_approved_at",
        "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date"
    ]),
    "order_items": ("olist_order_items_dataset.csv", [
        "order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_date", "price", "freight_value"
    ]),
    "order_payments": ("olist_order_payments_dataset.csv", [
        "order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value"
    ]),
    "order_reviews": ("olist_order_reviews_dataset.csv", [
        "review_id", "order_id", "review_score", "review_comment_title", "review_comment_message",
        "review_creation_date", "review_answer_timestamp"
    ]),
    "geolocation": ("olist_geolocation_dataset.csv", [
        "geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng", "geolocation_city", "geolocation_state"
    ]),
}

CLEAN_TABLES = {
    "olist_customers_dataset.csv": "stg_clean_customers",
    "olist_sellers_dataset.csv": "stg_clean_sellers",
    "product_category_name_translation.csv": "stg_clean_categories",
    "olist_products_dataset.csv": "stg_clean_products",
    "olist_orders_dataset.csv": "stg_clean_orders",
    "olist_order_items_dataset.csv": "stg_clean_order_items",
    "olist_order_payments_dataset.csv": "stg_clean_order_payments",
    "olist_order_reviews_dataset.csv": "stg_clean_order_reviews",
    "olist_geolocation_dataset.csv": "stg_clean_geolocation",
}


def configure_logging(batch_id: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(LOG_DIR / f"etl_{batch_id}.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def run_python(*args: object) -> None:
    command = [sys.executable, *(str(arg) for arg in args)]
    logging.info("Menjalankan %s", Path(str(args[0])).name)
    subprocess.run(command, check=True)


def import_mysql_dump(path: Path) -> None:
    environment = os.environ.copy()
    if MYSQL_PASSWORD:
        environment["MYSQL_PWD"] = MYSQL_PASSWORD
    command = [
        str(MYSQL_CLIENT),
        f"--host={MYSQL_HOST}",
        f"--port={MYSQL_PORT}",
        f"--user={MYSQL_USER}",
        "--default-character-set=utf8mb4",
        f"--execute=source {path.resolve().as_posix()}",
    ]
    logging.info("Mengimpor DWH ke MySQL Laragon")
    subprocess.run(command, check=True, env=environment)


def start_batch(batch_id: str, mode: str, business_date: date, watermark_end: datetime) -> datetime | None:
    connection = connect(STAGING_DB)
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT MIN(last_successful_watermark) FROM etl_watermark WHERE pipeline_name=%s",
            (PIPELINE_NAME,),
        )
        watermark_start = cursor.fetchone()[0]
        if mode == "full":
            watermark_start = None
        cursor.execute(
            """
            INSERT INTO etl_batch(
              batch_id,pipeline_name,load_mode,business_date,started_at,
              watermark_start,watermark_end,status
            ) VALUES(%s,%s,%s,%s,NOW(6),%s,%s,'RUNNING')
            """,
            (batch_id, PIPELINE_NAME, mode, business_date, watermark_start, watermark_end.replace(tzinfo=None)),
        )
        connection.commit()
        return watermark_start
    finally:
        connection.close()


def extract_to_raw_staging(batch_id: str, mode: str, watermark_start: datetime | None, watermark_end: datetime) -> int:
    connection = connect()
    total = 0
    try:
        cursor = connection.cursor()
        for table in SOURCE_TABLES:
            staging_table = f"stg_raw_{table}"
            if mode == "full":
                cursor.execute(f"DROP TABLE IF EXISTS `{STAGING_DB}`.`{staging_table}`")
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS `{STAGING_DB}`.`{staging_table}` AS
                SELECT CAST('' AS CHAR(36)) AS batch_id,
                       CAST(NOW(6) AS DATETIME(6)) AS extracted_at,
                       source.*
                FROM `{OLTP_DB}`.`{table}` source
                WHERE 1=0
                """
            )
            where = "source.source_updated_at <= %s"
            params: list[object] = [batch_id, watermark_end.replace(tzinfo=None)]
            if mode == "incremental" and watermark_start is not None:
                where += " AND source.source_updated_at > %s"
                params.append(watermark_start)
            cursor.execute(
                f"""
                INSERT INTO `{STAGING_DB}`.`{staging_table}`
                SELECT %s, NOW(6), source.*
                FROM `{OLTP_DB}`.`{table}` source
                WHERE {where}
                """,
                tuple(params),
            )
            total += cursor.rowcount
            logging.info("Extract %s: %s baris", table, cursor.rowcount)
        connection.commit()
    finally:
        connection.close()
    return total


def export_oltp_snapshot(batch_dir: Path) -> Path:
    snapshot_dir = batch_dir / "oltp_snapshot"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    db_engine = engine(OLTP_DB)
    for table, (filename, columns) in SOURCE_TABLES.items():
        path = snapshot_dir / filename
        query = text(f"SELECT {','.join(f'`{column}`' for column in columns)} FROM `{table}`")
        first = True
        with db_engine.connect() as connection:
            for chunk in pd.read_sql(query, connection, chunksize=50000):
                chunk.to_csv(path, mode="w" if first else "a", header=first, index=False, encoding="utf-8", lineterminator="\n")
                first = False
        logging.info("Snapshot OLTP: %s", filename)

    zip_path = batch_dir / "oltp_snapshot.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(snapshot_dir.glob("*.csv")):
            archive.write(path, path.name)
    return zip_path


def load_clean_staging(batch_id: str, quality_dir: Path) -> tuple[int, int]:
    db_engine = engine(STAGING_DB)
    clean_total = 0
    for filename, table in CLEAN_TABLES.items():
        frame = pd.read_csv(quality_dir / "clean" / filename, low_memory=False)
        frame.insert(0, "batch_id", batch_id)
        frame.to_sql(table, db_engine, if_exists="replace", index=False, chunksize=3000)
        clean_total += len(frame)

    metadata = quality_dir / "metadata"
    rules = pd.read_csv(metadata / "quality_rule_results.csv")
    rules.insert(0, "batch_id", batch_id)
    rules = rules.rename(columns={"dimension": "dimension_name"})
    rules.to_sql("dq_rule_result", db_engine, if_exists="append", index=False, chunksize=1000)

    issues = pd.read_csv(metadata / "quality_issues.csv", low_memory=False)
    issues.insert(0, "batch_id", batch_id)
    issue_rows = issues.rename(
        columns={
            "table": "source_table",
            "dimension": "dimension_name",
            "column": "column_name",
            "action": "action_taken",
        }
    )[
        [
            "batch_id", "source_table", "record_key", "rule_id", "dimension_name", "severity",
            "column_name", "original_value", "action_taken", "disposition", "detail"
        ]
    ]
    issue_rows.to_sql("dq_issue_detail", db_engine, if_exists="append", index=False, chunksize=2000)

    rejects = issue_rows.loc[issue_rows["disposition"].eq("quarantined")].copy()
    reject_count = len(rejects)
    if reject_count:
        rejects = rejects.rename(columns={"record_key": "business_key", "detail": "rejection_reason"})
        rejects["raw_record"] = None
        rejects[
            [
                "batch_id", "source_table", "business_key", "rule_id", "dimension_name", "severity",
                "column_name", "original_value", "rejection_reason", "raw_record"
            ]
        ].to_sql("etl_reject", db_engine, if_exists="append", index=False, chunksize=1000)

    transforms = pd.read_csv(metadata / "transformation_log.csv")
    transforms.insert(0, "batch_id", batch_id)
    transforms = transforms.rename(
        columns={"table": "source_table", "action": "action_name"}
    )[["batch_id", "source_table", "action_name", "affected_rows", "detail"]]
    transforms.to_sql("dq_transformation_log", db_engine, if_exists="append", index=False)

    profiles = pd.read_csv(metadata / "table_profile.csv")
    profiles.insert(0, "batch_id", batch_id)
    profiles = profiles.rename(columns={"table": "table_name"})
    profiles.to_sql("dq_table_profile", db_engine, if_exists="append", index=False)
    return clean_total, reject_count


def build_and_publish_dwh(batch_dir: Path, quality_dir: Path) -> None:
    sqlite_output = batch_dir / "sqlite_dwh"
    run_python(
        SQLITE_DWH_SCRIPT,
        "--source-dir", quality_dir / "clean",
        "--output-dir", sqlite_output,
        "--schema", SQLITE_SCHEMA,
    )
    mysql_dump = batch_dir / "olist_dwh_mysql.sql"
    run_python(
        MYSQL_EXPORT_SCRIPT,
        "--sqlite-db", sqlite_output / "olist_dwh.sqlite",
        "--schema", MYSQL_SCHEMA,
        "--output", mysql_dump,
    )
    import_mysql_dump(mysql_dump)
    run_sql_file(PROJECT_ROOT / "sql" / "04_create_data_marts.sql")


def validate_mysql() -> dict[str, object]:
    connection = connect(DWH_DB)
    try:
        cursor = connection.cursor()
        queries = {
            "fact_order_rows": "SELECT COUNT(*) FROM fact_order",
            "fact_sales_rows": "SELECT COUNT(*) FROM fact_sales",
            "fact_payment_rows": "SELECT COUNT(*) FROM fact_payment",
            "fact_review_rows": "SELECT COUNT(*) FROM fact_review",
            "fact_order_event_rows": "SELECT COUNT(*) FROM fact_order_event",
            "gross_sales": "SELECT ROUND(SUM(line_total),2) FROM fact_sales",
            "payment_value": "SELECT ROUND(SUM(payment_value),2) FROM fact_payment",
            "failed_checks": "SELECT COUNT(*) FROM etl_validation_result WHERE status='FAIL'",
            "monthly_mart_rows": "SELECT COUNT(*) FROM mart_monthly_sales",
        }
        results = {}
        for name, query in queries.items():
            cursor.execute(query)
            results[name] = cursor.fetchone()[0]
        if results["failed_checks"] != 0:
            raise RuntimeError(f"Validasi DWH gagal: {results}")
        return results
    finally:
        connection.close()


def finish_batch(
    batch_id: str,
    status: str,
    source_rows: int,
    clean_rows: int,
    rejected_rows: int,
    watermark_end: datetime,
    message: str,
) -> None:
    connection = connect(STAGING_DB)
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            UPDATE etl_batch
            SET completed_at=NOW(6),status=%s,source_rows=%s,clean_rows=%s,rejected_rows=%s,message=%s
            WHERE batch_id=%s
            """,
            (status, source_rows, clean_rows, rejected_rows, message, batch_id),
        )
        if status == "SUCCESS":
            for table in SOURCE_TABLES:
                cursor.execute(
                    """
                    INSERT INTO etl_watermark(pipeline_name,source_table,last_successful_watermark,last_batch_id)
                    VALUES(%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE
                      last_successful_watermark=VALUES(last_successful_watermark),
                      last_batch_id=VALUES(last_batch_id)
                    """,
                    (PIPELINE_NAME, table, watermark_end.replace(tzinfo=None), batch_id),
                )
        connection.commit()
    finally:
        connection.close()


def create_dashboard_user() -> None:
    user = os.getenv("DASHBOARD_USER", "olist_dashboard").replace("'", "''")
    password = os.getenv("DASHBOARD_PASSWORD", "olist_dashboard_local").replace("'", "''")
    connection = connect()
    try:
        cursor = connection.cursor()
        cursor.execute(f"CREATE USER IF NOT EXISTS '{user}'@'localhost' IDENTIFIED BY '{password}'")
        cursor.execute(f"ALTER USER '{user}'@'localhost' IDENTIFIED BY '{password}'")
        cursor.execute(f"GRANT SELECT ON `{DWH_DB}`.* TO '{user}'@'localhost'")
        cursor.execute(f"GRANT SELECT ON `{STAGING_DB}`.etl_batch TO '{user}'@'localhost'")
        cursor.execute(f"GRANT SELECT ON `{STAGING_DB}`.dq_rule_result TO '{user}'@'localhost'")
        connection.commit()
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline OLTP → staging → data quality → DWH.")
    parser.add_argument("--mode", choices=["full", "incremental"], default="incremental")
    parser.add_argument("--business-date", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()

    batch_id = str(uuid.uuid4())
    configure_logging(batch_id)
    run_sql_file(PROJECT_ROOT / "sql" / "02_create_staging.sql")
    batch_dir = RUNTIME_DIR / "batches" / batch_id
    batch_dir.mkdir(parents=True, exist_ok=False)
    clock_connection = connect()
    try:
        clock_cursor = clock_connection.cursor()
        clock_cursor.execute("SELECT NOW(6)")
        watermark_end = clock_cursor.fetchone()[0]
    finally:
        clock_connection.close()
    watermark_start = start_batch(batch_id, args.mode, args.business_date, watermark_end)
    source_rows = clean_rows = rejected_rows = 0

    try:
        logging.info("Batch %s dimulai (%s)", batch_id, args.mode)
        source_rows = extract_to_raw_staging(batch_id, args.mode, watermark_start, watermark_end)
        snapshot_zip = export_oltp_snapshot(batch_dir)
        quality_dir = batch_dir / "quality"
        run_python(QUALITY_SCRIPT, "--input-zip", snapshot_zip, "--output-dir", quality_dir)
        clean_rows, rejected_rows = load_clean_staging(batch_id, quality_dir)
        build_and_publish_dwh(batch_dir, quality_dir)
        create_dashboard_user()
        validation = validate_mysql()
        finish_batch(
            batch_id, "SUCCESS", source_rows, clean_rows, rejected_rows, watermark_end,
            json.dumps(validation, default=str),
        )
        summary = {
            "batch_id": batch_id,
            "mode": args.mode,
            "business_date": args.business_date.isoformat(),
            "status": "SUCCESS",
            "source_rows_extracted": source_rows,
            "clean_rows": clean_rows,
            "rejected_issue_rows": rejected_rows,
            "validation": validation,
            "batch_directory": str(batch_dir),
        }
        (RUNTIME_DIR / "latest_run.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        print(json.dumps(summary, indent=2, default=str))
    except Exception as exc:
        logging.exception("Pipeline gagal")
        finish_batch(batch_id, "FAILED", source_rows, clean_rows, rejected_rows, watermark_end, str(exc))
        raise


if __name__ == "__main__":
    main()
