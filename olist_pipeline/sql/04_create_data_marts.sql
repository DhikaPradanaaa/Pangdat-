USE olist_dwh;

CREATE TABLE IF NOT EXISTS dim_payment_type (
  payment_type_key INT AUTO_INCREMENT PRIMARY KEY,
  payment_type VARCHAR(32) NOT NULL UNIQUE
) ENGINE=InnoDB;

INSERT IGNORE INTO dim_payment_type(payment_type)
SELECT DISTINCT payment_type FROM fact_payment;

CREATE TABLE IF NOT EXISTS dim_order_status (
  order_status_key INT AUTO_INCREMENT PRIMARY KEY,
  order_status VARCHAR(32) NOT NULL UNIQUE
) ENGINE=InnoDB;

INSERT IGNORE INTO dim_order_status(order_status)
SELECT DISTINCT order_status FROM fact_order;

DROP TABLE IF EXISTS fact_order_event;
CREATE TABLE fact_order_event (
  order_event_key BIGINT AUTO_INCREMENT PRIMARY KEY,
  order_key INT NOT NULL,
  order_id CHAR(32) NOT NULL,
  event_type VARCHAR(40) NOT NULL,
  event_timestamp DATETIME NOT NULL,
  event_date_key INT NOT NULL,
  UNIQUE KEY uq_order_event (order_id, event_type),
  CONSTRAINT fk_event_order FOREIGN KEY(order_key) REFERENCES fact_order(order_key),
  CONSTRAINT fk_event_date FOREIGN KEY(event_date_key) REFERENCES dim_date(date_key),
  INDEX idx_event_type_date(event_type, event_date_key)
) ENGINE=InnoDB;

INSERT INTO fact_order_event(order_key, order_id, event_type, event_timestamp, event_date_key)
SELECT order_key, order_id, 'purchased', purchase_timestamp, purchase_date_key FROM fact_order
UNION ALL
SELECT order_key, order_id, 'approved', approved_timestamp, approved_date_key FROM fact_order WHERE approved_timestamp IS NOT NULL
UNION ALL
SELECT order_key, order_id, 'handed_to_carrier', carrier_timestamp, carrier_date_key FROM fact_order WHERE carrier_timestamp IS NOT NULL
UNION ALL
SELECT order_key, order_id, 'delivered', delivered_timestamp, delivered_date_key FROM fact_order WHERE delivered_timestamp IS NOT NULL
UNION ALL
SELECT order_key, order_id, 'estimated_delivery', estimated_delivery_timestamp, estimated_delivery_date_key FROM fact_order WHERE estimated_delivery_timestamp IS NOT NULL;

CREATE OR REPLACE VIEW mart_daily_sales AS
SELECT d.full_date,
       COUNT(DISTINCT s.order_key) AS order_count,
       COUNT(*) AS item_count,
       ROUND(SUM(s.price),2) AS product_revenue,
       ROUND(SUM(s.freight_value),2) AS freight_revenue,
       ROUND(SUM(s.line_total),2) AS gross_sales
FROM fact_sales s
JOIN dim_date d ON d.date_key=s.purchase_date_key
GROUP BY d.full_date;

CREATE OR REPLACE VIEW mart_monthly_sales AS
SELECT * FROM vw_monthly_sales;

CREATE OR REPLACE VIEW mart_category_performance AS
SELECT * FROM vw_product_sales;

CREATE OR REPLACE VIEW mart_delivery_performance AS
SELECT d.year_number,
       d.month_number,
       COUNT(*) AS order_count,
       SUM(o.is_delivered) AS delivered_orders,
       SUM(o.is_late) AS late_orders,
       ROUND(100.0*SUM(o.is_late)/NULLIF(SUM(o.is_delivered),0),2) AS late_percent,
       ROUND(AVG(o.delivery_days),2) AS avg_delivery_days
FROM fact_order o
JOIN dim_date d ON d.date_key=o.purchase_date_key
GROUP BY d.year_number,d.month_number;

CREATE OR REPLACE VIEW mart_customer_experience AS
SELECT o.is_late,
       COUNT(*) AS review_count,
       ROUND(AVG(r.review_score),2) AS average_review_score,
       ROUND(AVG(r.response_hours),2) AS average_response_hours
FROM fact_review r
JOIN fact_order o ON o.order_key=r.order_key
GROUP BY o.is_late;

CREATE OR REPLACE VIEW mart_payment_summary AS
SELECT payment_type,
       COUNT(DISTINCT order_key) AS order_count,
       COUNT(*) AS payment_count,
       ROUND(SUM(payment_value),2) AS payment_value
FROM fact_payment
GROUP BY payment_type;

CREATE OR REPLACE VIEW mart_data_quality AS
SELECT b.batch_id,
       b.business_date,
       b.completed_at,
       b.status,
       b.source_rows,
       b.clean_rows,
       b.rejected_rows,
       COALESCE(SUM(r.detected_count),0) AS detected_issues,
       COALESCE(SUM(r.corrected_count),0) AS corrected_issues,
       COALESCE(SUM(r.open_count),0) AS open_issues,
       COALESCE(SUM(r.quarantined_count),0) AS quarantined_issues
FROM olist_staging.etl_batch b
LEFT JOIN olist_staging.dq_rule_result r ON r.batch_id=b.batch_id
GROUP BY b.batch_id,b.business_date,b.completed_at,b.status,b.source_rows,b.clean_rows,b.rejected_rows;
