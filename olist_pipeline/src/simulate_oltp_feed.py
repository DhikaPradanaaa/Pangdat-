from __future__ import annotations

import argparse
import json

from config import OLTP_DB
from database import connect


def main() -> None:
    parser = argparse.ArgumentParser(description="Tandai order terbaru sebagai perubahan OLTP untuk demo incremental.")
    parser.add_argument("--touch-latest", type=int, default=25)
    args = parser.parse_args()

    connection = connect(OLTP_DB)
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT order_id FROM orders ORDER BY order_purchase_timestamp DESC LIMIT %s",
            (args.touch_latest,),
        )
        order_ids = [row[0] for row in cursor.fetchall()]
        placeholders = ",".join(["%s"] * len(order_ids))
        counts = {}
        for table in ["orders", "order_items", "order_payments", "order_reviews"]:
            cursor.execute(
                f"UPDATE `{table}` SET source_updated_at=NOW(6) WHERE order_id IN ({placeholders})",
                tuple(order_ids),
            )
            counts[table] = cursor.rowcount
        connection.commit()
    finally:
        connection.close()
    print(json.dumps({"status":"SUCCESS","touched_orders":len(order_ids),"updated_rows":counts}, indent=2))


if __name__ == "__main__":
    main()
