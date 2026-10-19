from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from config import DWH_DB, OLTP_DB, STAGING_DB
from database import connect


def scalar(database: str, query: str):
    connection = connect(database)
    try:
        cursor = connection.cursor()
        cursor.execute(query)
        return cursor.fetchone()[0]
    finally:
        connection.close()


def test_oltp_loaded():
    assert scalar(OLTP_DB, "SELECT COUNT(*) FROM orders") >= 99441


def test_latest_batch_success():
    assert scalar(STAGING_DB, "SELECT status FROM etl_batch ORDER BY started_at DESC LIMIT 1") == "SUCCESS"


def test_no_failed_dwh_validation():
    assert scalar(DWH_DB, "SELECT COUNT(*) FROM etl_validation_result WHERE status='FAIL'") == 0


def test_fact_grain_unique():
    duplicates = scalar(
        DWH_DB,
        "SELECT COUNT(*) FROM (SELECT order_id,order_item_id,COUNT(*) c FROM fact_sales GROUP BY order_id,order_item_id HAVING c>1) x",
    )
    assert duplicates == 0


def test_data_mart_available():
    assert scalar(DWH_DB, "SELECT COUNT(*) FROM mart_monthly_sales") > 0
