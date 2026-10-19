SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

CREATE DATABASE IF NOT EXISTS olist_dwh
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;
USE olist_dwh;

DROP VIEW IF EXISTS vw_product_sales;
DROP VIEW IF EXISTS vw_monthly_sales;
DROP VIEW IF EXISTS vw_order_summary;

DROP TABLE IF EXISTS etl_validation_result;
DROP TABLE IF EXISTS etl_reject;
DROP TABLE IF EXISTS fact_review;
DROP TABLE IF EXISTS fact_payment;
DROP TABLE IF EXISTS fact_sales;
DROP TABLE IF EXISTS fact_order;
DROP TABLE IF EXISTS dim_product;
DROP TABLE IF EXISTS dim_seller;
DROP TABLE IF EXISTS dim_customer;
DROP TABLE IF EXISTS dim_geolocation;
DROP TABLE IF EXISTS dim_date;
DROP TABLE IF EXISTS etl_run;

CREATE TABLE etl_run (
    run_id CHAR(36) PRIMARY KEY,
    started_at_utc VARCHAR(35) NOT NULL,
    completed_at_utc VARCHAR(35),
    status VARCHAR(32) NOT NULL,
    source_directory VARCHAR(1024) NOT NULL,
    include_error_rows TINYINT(1) NOT NULL,
    source_row_count BIGINT,
    loaded_row_count BIGINT,
    rejected_row_count BIGINT,
    notes TEXT,
    CONSTRAINT chk_etl_run_include_errors CHECK (include_error_rows IN (0, 1))
) ENGINE=InnoDB;

CREATE TABLE dim_date (
    date_key INT PRIMARY KEY,
    full_date DATE UNIQUE,
    day_of_month TINYINT,
    day_name VARCHAR(16),
    day_of_week TINYINT,
    week_of_year TINYINT,
    month_number TINYINT,
    month_name VARCHAR(16),
    quarter_number TINYINT,
    year_number SMALLINT,
    is_weekend TINYINT(1),
    CONSTRAINT chk_dim_date_weekend CHECK (is_weekend IN (0, 1))
) ENGINE=InnoDB;

CREATE TABLE dim_geolocation (
    geolocation_key INT PRIMARY KEY,
    zip_code_prefix VARCHAR(16) NOT NULL UNIQUE,
    city VARCHAR(255),
    state CHAR(2),
    latitude DECIMAL(11,8),
    longitude DECIMAL(11,8),
    valid_coordinate_count INT,
    source_point_count INT,
    source_city_state_count INT,
    conflict_flag TINYINT(1),
    dq_status VARCHAR(16) NOT NULL,
    dq_issue_codes VARCHAR(1024),
    CONSTRAINT chk_dim_geo_conflict CHECK (conflict_flag IN (0, 1))
) ENGINE=InnoDB;

CREATE TABLE dim_customer (
    customer_key INT PRIMARY KEY,
    customer_id CHAR(32) NOT NULL UNIQUE,
    customer_unique_id CHAR(32) NOT NULL,
    zip_code_prefix VARCHAR(16),
    geolocation_key INT NOT NULL DEFAULT 0,
    city VARCHAR(255),
    state CHAR(2),
    dq_status VARCHAR(16) NOT NULL,
    dq_issue_codes VARCHAR(1024),
    CONSTRAINT fk_customer_geolocation
        FOREIGN KEY (geolocation_key) REFERENCES dim_geolocation (geolocation_key)
) ENGINE=InnoDB;

CREATE TABLE dim_seller (
    seller_key INT PRIMARY KEY,
    seller_id CHAR(32) NOT NULL UNIQUE,
    zip_code_prefix VARCHAR(16),
    geolocation_key INT NOT NULL DEFAULT 0,
    city VARCHAR(255),
    state CHAR(2),
    dq_status VARCHAR(16) NOT NULL,
    dq_issue_codes VARCHAR(1024),
    CONSTRAINT fk_seller_geolocation
        FOREIGN KEY (geolocation_key) REFERENCES dim_geolocation (geolocation_key)
) ENGINE=InnoDB;

CREATE TABLE dim_product (
    product_key INT PRIMARY KEY,
    product_id CHAR(32) NOT NULL UNIQUE,
    category_name VARCHAR(255),
    category_name_english VARCHAR(255),
    translation_status VARCHAR(32),
    product_name_length INT,
    product_description_length INT,
    product_photos_qty INT,
    product_weight_g DECIMAL(12,3),
    product_length_cm DECIMAL(12,3),
    product_height_cm DECIMAL(12,3),
    product_width_cm DECIMAL(12,3),
    dq_status VARCHAR(16) NOT NULL,
    dq_issue_codes VARCHAR(1024)
) ENGINE=InnoDB;

CREATE TABLE fact_order (
    order_key INT PRIMARY KEY,
    order_id CHAR(32) NOT NULL UNIQUE,
    customer_key INT NOT NULL,
    purchase_date_key INT NOT NULL,
    approved_date_key INT NOT NULL DEFAULT 0,
    carrier_date_key INT NOT NULL DEFAULT 0,
    delivered_date_key INT NOT NULL DEFAULT 0,
    estimated_delivery_date_key INT NOT NULL DEFAULT 0,
    order_status VARCHAR(32) NOT NULL,
    purchase_timestamp DATETIME NOT NULL,
    approved_timestamp DATETIME,
    carrier_timestamp DATETIME,
    delivered_timestamp DATETIME,
    estimated_delivery_timestamp DATETIME,
    calculated_order_total DECIMAL(14,2),
    recorded_payment_total DECIMAL(14,2),
    payment_difference DECIMAL(14,2),
    approval_hours DECIMAL(14,4),
    carrier_lead_hours DECIMAL(14,4),
    delivery_days DECIMAL(14,4),
    delay_days DECIMAL(14,4),
    is_delivered TINYINT(1) NOT NULL,
    is_late TINYINT(1) NOT NULL,
    dq_status VARCHAR(16) NOT NULL,
    dq_issue_codes VARCHAR(1024),
    CONSTRAINT chk_order_delivered CHECK (is_delivered IN (0, 1)),
    CONSTRAINT chk_order_late CHECK (is_late IN (0, 1)),
    CONSTRAINT fk_order_customer FOREIGN KEY (customer_key) REFERENCES dim_customer (customer_key),
    CONSTRAINT fk_order_purchase_date FOREIGN KEY (purchase_date_key) REFERENCES dim_date (date_key),
    CONSTRAINT fk_order_approved_date FOREIGN KEY (approved_date_key) REFERENCES dim_date (date_key),
    CONSTRAINT fk_order_carrier_date FOREIGN KEY (carrier_date_key) REFERENCES dim_date (date_key),
    CONSTRAINT fk_order_delivered_date FOREIGN KEY (delivered_date_key) REFERENCES dim_date (date_key),
    CONSTRAINT fk_order_estimated_date FOREIGN KEY (estimated_delivery_date_key) REFERENCES dim_date (date_key)
) ENGINE=InnoDB;

CREATE TABLE fact_sales (
    sales_key INT PRIMARY KEY,
    order_key INT NOT NULL,
    order_id CHAR(32) NOT NULL,
    order_item_id INT NOT NULL,
    product_key INT NOT NULL,
    seller_key INT NOT NULL,
    purchase_date_key INT NOT NULL,
    shipping_limit_date_key INT NOT NULL DEFAULT 0,
    shipping_limit_timestamp DATETIME,
    price DECIMAL(14,2) NOT NULL,
    freight_value DECIMAL(14,2) NOT NULL,
    line_total DECIMAL(14,2) NOT NULL,
    dq_status VARCHAR(16) NOT NULL,
    dq_issue_codes VARCHAR(1024),
    UNIQUE KEY uq_sales_grain (order_id, order_item_id),
    CONSTRAINT fk_sales_order FOREIGN KEY (order_key) REFERENCES fact_order (order_key),
    CONSTRAINT fk_sales_product FOREIGN KEY (product_key) REFERENCES dim_product (product_key),
    CONSTRAINT fk_sales_seller FOREIGN KEY (seller_key) REFERENCES dim_seller (seller_key),
    CONSTRAINT fk_sales_purchase_date FOREIGN KEY (purchase_date_key) REFERENCES dim_date (date_key),
    CONSTRAINT fk_sales_shipping_date FOREIGN KEY (shipping_limit_date_key) REFERENCES dim_date (date_key)
) ENGINE=InnoDB;

CREATE TABLE fact_payment (
    payment_key INT PRIMARY KEY,
    order_key INT NOT NULL,
    order_id CHAR(32) NOT NULL,
    payment_sequential INT NOT NULL,
    purchase_date_key INT NOT NULL,
    payment_type VARCHAR(32) NOT NULL,
    payment_installments INT NOT NULL,
    payment_value DECIMAL(14,2) NOT NULL,
    dq_status VARCHAR(16) NOT NULL,
    dq_issue_codes VARCHAR(1024),
    UNIQUE KEY uq_payment_grain (order_id, payment_sequential),
    CONSTRAINT fk_payment_order FOREIGN KEY (order_key) REFERENCES fact_order (order_key),
    CONSTRAINT fk_payment_purchase_date FOREIGN KEY (purchase_date_key) REFERENCES dim_date (date_key)
) ENGINE=InnoDB;

CREATE TABLE fact_review (
    review_key INT PRIMARY KEY,
    review_business_key VARCHAR(80) NOT NULL UNIQUE,
    review_id CHAR(32) NOT NULL,
    order_key INT NOT NULL,
    order_id CHAR(32) NOT NULL,
    creation_date_key INT NOT NULL DEFAULT 0,
    answer_date_key INT NOT NULL DEFAULT 0,
    review_score TINYINT NOT NULL,
    review_comment_title TEXT,
    review_comment_message LONGTEXT,
    creation_timestamp DATETIME,
    answer_timestamp DATETIME,
    response_hours DECIMAL(14,4),
    dq_status VARCHAR(16) NOT NULL,
    dq_issue_codes VARCHAR(1024),
    CONSTRAINT chk_review_score CHECK (review_score BETWEEN 1 AND 5),
    CONSTRAINT fk_review_order FOREIGN KEY (order_key) REFERENCES fact_order (order_key),
    CONSTRAINT fk_review_creation_date FOREIGN KEY (creation_date_key) REFERENCES dim_date (date_key),
    CONSTRAINT fk_review_answer_date FOREIGN KEY (answer_date_key) REFERENCES dim_date (date_key)
) ENGINE=InnoDB;

CREATE TABLE etl_reject (
    reject_key BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id CHAR(36) NOT NULL,
    source_table VARCHAR(128) NOT NULL,
    business_key VARCHAR(255),
    rejection_reason VARCHAR(255) NOT NULL,
    dq_status VARCHAR(16),
    dq_issue_codes VARCHAR(1024),
    CONSTRAINT fk_reject_run FOREIGN KEY (run_id) REFERENCES etl_run (run_id)
) ENGINE=InnoDB;

CREATE TABLE etl_validation_result (
    validation_key BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id CHAR(36) NOT NULL,
    check_name VARCHAR(255) NOT NULL,
    status VARCHAR(16) NOT NULL,
    expected_value TEXT,
    actual_value TEXT,
    detail TEXT,
    CONSTRAINT fk_validation_run FOREIGN KEY (run_id) REFERENCES etl_run (run_id)
) ENGINE=InnoDB;

CREATE INDEX idx_customer_unique_id ON dim_customer (customer_unique_id);
CREATE INDEX idx_customer_geo ON dim_customer (geolocation_key);
CREATE INDEX idx_seller_geo ON dim_seller (geolocation_key);
CREATE INDEX idx_product_category ON dim_product (category_name_english);
CREATE INDEX idx_order_customer ON fact_order (customer_key);
CREATE INDEX idx_order_purchase_date ON fact_order (purchase_date_key);
CREATE INDEX idx_order_status ON fact_order (order_status);
CREATE INDEX idx_sales_order ON fact_sales (order_key);
CREATE INDEX idx_sales_product ON fact_sales (product_key);
CREATE INDEX idx_sales_seller ON fact_sales (seller_key);
CREATE INDEX idx_sales_purchase_date ON fact_sales (purchase_date_key);
CREATE INDEX idx_payment_order ON fact_payment (order_key);
CREATE INDEX idx_payment_purchase_date ON fact_payment (purchase_date_key);
CREATE INDEX idx_review_order ON fact_review (order_key);
CREATE INDEX idx_review_creation_date ON fact_review (creation_date_key);

CREATE VIEW vw_order_summary AS
WITH item_totals AS (
    SELECT order_key,
           COUNT(*) AS item_count,
           SUM(price) AS item_value,
           SUM(freight_value) AS freight_value,
           SUM(line_total) AS sales_value
    FROM fact_sales
    GROUP BY order_key
),
payment_totals AS (
    SELECT order_key,
           COUNT(*) AS payment_count,
           SUM(payment_value) AS payment_value
    FROM fact_payment
    GROUP BY order_key
),
review_totals AS (
    SELECT order_key,
           COUNT(*) AS review_count,
           AVG(review_score) AS average_review_score
    FROM fact_review
    GROUP BY order_key
)
SELECT o.order_key,
       o.order_id,
       o.order_status,
       o.purchase_date_key,
       o.customer_key,
       COALESCE(i.item_count, 0) AS item_count,
       COALESCE(i.item_value, 0) AS item_value,
       COALESCE(i.freight_value, 0) AS freight_value,
       COALESCE(i.sales_value, 0) AS sales_value,
       COALESCE(p.payment_count, 0) AS payment_count,
       COALESCE(p.payment_value, 0) AS payment_value,
       COALESCE(r.review_count, 0) AS review_count,
       r.average_review_score,
       o.delivery_days,
       o.delay_days,
       o.is_late,
       o.dq_status
FROM fact_order o
LEFT JOIN item_totals i ON i.order_key = o.order_key
LEFT JOIN payment_totals p ON p.order_key = o.order_key
LEFT JOIN review_totals r ON r.order_key = o.order_key;

CREATE VIEW vw_monthly_sales AS
SELECT d.year_number,
       d.month_number,
       d.month_name,
       COUNT(DISTINCT s.order_key) AS order_count,
       COUNT(*) AS item_count,
       SUM(s.price) AS product_revenue,
       SUM(s.freight_value) AS freight_revenue,
       SUM(s.line_total) AS gross_sales
FROM fact_sales s
JOIN dim_date d ON d.date_key = s.purchase_date_key
GROUP BY d.year_number, d.month_number, d.month_name;

CREATE VIEW vw_product_sales AS
SELECT p.category_name,
       p.category_name_english,
       COUNT(DISTINCT s.order_key) AS order_count,
       COUNT(*) AS item_count,
       SUM(s.line_total) AS gross_sales,
       AVG(s.price) AS average_item_price
FROM fact_sales s
JOIN dim_product p ON p.product_key = s.product_key
GROUP BY p.category_name, p.category_name_english;

SET FOREIGN_KEY_CHECKS = 1;
