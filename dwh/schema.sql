PRAGMA foreign_keys = ON;

CREATE TABLE etl_run (
    run_id TEXT PRIMARY KEY,
    started_at_utc TEXT NOT NULL,
    completed_at_utc TEXT,
    status TEXT NOT NULL,
    source_directory TEXT NOT NULL,
    include_error_rows INTEGER NOT NULL CHECK (include_error_rows IN (0, 1)),
    source_row_count INTEGER,
    loaded_row_count INTEGER,
    rejected_row_count INTEGER,
    notes TEXT
);

CREATE TABLE dim_date (
    date_key INTEGER PRIMARY KEY,
    full_date TEXT UNIQUE,
    day_of_month INTEGER,
    day_name TEXT,
    day_of_week INTEGER,
    week_of_year INTEGER,
    month_number INTEGER,
    month_name TEXT,
    quarter_number INTEGER,
    year_number INTEGER,
    is_weekend INTEGER CHECK (is_weekend IN (0, 1))
);

CREATE TABLE dim_geolocation (
    geolocation_key INTEGER PRIMARY KEY,
    zip_code_prefix TEXT NOT NULL UNIQUE,
    city TEXT,
    state TEXT,
    latitude REAL,
    longitude REAL,
    valid_coordinate_count INTEGER,
    source_point_count INTEGER,
    source_city_state_count INTEGER,
    conflict_flag INTEGER CHECK (conflict_flag IN (0, 1)),
    dq_status TEXT NOT NULL,
    dq_issue_codes TEXT
);

CREATE TABLE dim_customer (
    customer_key INTEGER PRIMARY KEY,
    customer_id TEXT NOT NULL UNIQUE,
    customer_unique_id TEXT NOT NULL,
    zip_code_prefix TEXT,
    geolocation_key INTEGER NOT NULL DEFAULT 0,
    city TEXT,
    state TEXT,
    dq_status TEXT NOT NULL,
    dq_issue_codes TEXT,
    FOREIGN KEY (geolocation_key) REFERENCES dim_geolocation (geolocation_key)
);

CREATE TABLE dim_seller (
    seller_key INTEGER PRIMARY KEY,
    seller_id TEXT NOT NULL UNIQUE,
    zip_code_prefix TEXT,
    geolocation_key INTEGER NOT NULL DEFAULT 0,
    city TEXT,
    state TEXT,
    dq_status TEXT NOT NULL,
    dq_issue_codes TEXT,
    FOREIGN KEY (geolocation_key) REFERENCES dim_geolocation (geolocation_key)
);

CREATE TABLE dim_product (
    product_key INTEGER PRIMARY KEY,
    product_id TEXT NOT NULL UNIQUE,
    category_name TEXT,
    category_name_english TEXT,
    translation_status TEXT,
    product_name_length INTEGER,
    product_description_length INTEGER,
    product_photos_qty INTEGER,
    product_weight_g REAL,
    product_length_cm REAL,
    product_height_cm REAL,
    product_width_cm REAL,
    dq_status TEXT NOT NULL,
    dq_issue_codes TEXT
);

CREATE TABLE fact_order (
    order_key INTEGER PRIMARY KEY,
    order_id TEXT NOT NULL UNIQUE,
    customer_key INTEGER NOT NULL,
    purchase_date_key INTEGER NOT NULL,
    approved_date_key INTEGER NOT NULL DEFAULT 0,
    carrier_date_key INTEGER NOT NULL DEFAULT 0,
    delivered_date_key INTEGER NOT NULL DEFAULT 0,
    estimated_delivery_date_key INTEGER NOT NULL DEFAULT 0,
    order_status TEXT NOT NULL,
    purchase_timestamp TEXT NOT NULL,
    approved_timestamp TEXT,
    carrier_timestamp TEXT,
    delivered_timestamp TEXT,
    estimated_delivery_timestamp TEXT,
    calculated_order_total REAL,
    recorded_payment_total REAL,
    payment_difference REAL,
    approval_hours REAL,
    carrier_lead_hours REAL,
    delivery_days REAL,
    delay_days REAL,
    is_delivered INTEGER NOT NULL CHECK (is_delivered IN (0, 1)),
    is_late INTEGER NOT NULL CHECK (is_late IN (0, 1)),
    dq_status TEXT NOT NULL,
    dq_issue_codes TEXT,
    FOREIGN KEY (customer_key) REFERENCES dim_customer (customer_key),
    FOREIGN KEY (purchase_date_key) REFERENCES dim_date (date_key),
    FOREIGN KEY (approved_date_key) REFERENCES dim_date (date_key),
    FOREIGN KEY (carrier_date_key) REFERENCES dim_date (date_key),
    FOREIGN KEY (delivered_date_key) REFERENCES dim_date (date_key),
    FOREIGN KEY (estimated_delivery_date_key) REFERENCES dim_date (date_key)
);

CREATE TABLE fact_sales (
    sales_key INTEGER PRIMARY KEY,
    order_key INTEGER NOT NULL,
    order_id TEXT NOT NULL,
    order_item_id INTEGER NOT NULL,
    product_key INTEGER NOT NULL,
    seller_key INTEGER NOT NULL,
    purchase_date_key INTEGER NOT NULL,
    shipping_limit_date_key INTEGER NOT NULL DEFAULT 0,
    shipping_limit_timestamp TEXT,
    price REAL NOT NULL,
    freight_value REAL NOT NULL,
    line_total REAL NOT NULL,
    dq_status TEXT NOT NULL,
    dq_issue_codes TEXT,
    UNIQUE (order_id, order_item_id),
    FOREIGN KEY (order_key) REFERENCES fact_order (order_key),
    FOREIGN KEY (product_key) REFERENCES dim_product (product_key),
    FOREIGN KEY (seller_key) REFERENCES dim_seller (seller_key),
    FOREIGN KEY (purchase_date_key) REFERENCES dim_date (date_key),
    FOREIGN KEY (shipping_limit_date_key) REFERENCES dim_date (date_key)
);

CREATE TABLE fact_payment (
    payment_key INTEGER PRIMARY KEY,
    order_key INTEGER NOT NULL,
    order_id TEXT NOT NULL,
    payment_sequential INTEGER NOT NULL,
    purchase_date_key INTEGER NOT NULL,
    payment_type TEXT NOT NULL,
    payment_installments INTEGER NOT NULL,
    payment_value REAL NOT NULL,
    dq_status TEXT NOT NULL,
    dq_issue_codes TEXT,
    UNIQUE (order_id, payment_sequential),
    FOREIGN KEY (order_key) REFERENCES fact_order (order_key),
    FOREIGN KEY (purchase_date_key) REFERENCES dim_date (date_key)
);

CREATE TABLE fact_review (
    review_key INTEGER PRIMARY KEY,
    review_business_key TEXT NOT NULL UNIQUE,
    review_id TEXT NOT NULL,
    order_key INTEGER NOT NULL,
    order_id TEXT NOT NULL,
    creation_date_key INTEGER NOT NULL DEFAULT 0,
    answer_date_key INTEGER NOT NULL DEFAULT 0,
    review_score INTEGER NOT NULL CHECK (review_score BETWEEN 1 AND 5),
    review_comment_title TEXT,
    review_comment_message TEXT,
    creation_timestamp TEXT,
    answer_timestamp TEXT,
    response_hours REAL,
    dq_status TEXT NOT NULL,
    dq_issue_codes TEXT,
    FOREIGN KEY (order_key) REFERENCES fact_order (order_key),
    FOREIGN KEY (creation_date_key) REFERENCES dim_date (date_key),
    FOREIGN KEY (answer_date_key) REFERENCES dim_date (date_key)
);

CREATE TABLE etl_reject (
    reject_key INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    source_table TEXT NOT NULL,
    business_key TEXT,
    rejection_reason TEXT NOT NULL,
    dq_status TEXT,
    dq_issue_codes TEXT,
    FOREIGN KEY (run_id) REFERENCES etl_run (run_id)
);

CREATE TABLE etl_validation_result (
    validation_key INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    check_name TEXT NOT NULL,
    status TEXT NOT NULL,
    expected_value TEXT,
    actual_value TEXT,
    detail TEXT,
    FOREIGN KEY (run_id) REFERENCES etl_run (run_id)
);

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
