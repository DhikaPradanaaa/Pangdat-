-- Latihan OLTP -> staging -> DWH.
-- Jalankan di SQLyog ketika MySQL Laragon aktif.

USE olist_oltp;

SET @demo_name = 'lab_oltp_dwh_20261019_001';
SET @customer_id = MD5(CONCAT(@demo_name, '_customer'));
SET @customer_unique_id = MD5(CONCAT(@demo_name, '_customer_unique'));
SET @order_id = MD5(CONCAT(@demo_name, '_order'));
SET @review_id = MD5(CONCAT(@demo_name, '_review'));
SET @source_file = 'demo/01_insert_oltp.sql';

-- Gunakan produk, seller, dan lokasi yang memang sudah valid di OLTP.
SELECT oi.product_id, oi.seller_id
INTO @product_id, @seller_id
FROM order_items oi
JOIN products p ON p.product_id = oi.product_id
JOIN sellers s ON s.seller_id = oi.seller_id
ORDER BY oi.order_id, oi.order_item_id
LIMIT 1;

SELECT c.customer_zip_code_prefix, c.customer_city, c.customer_state
INTO @zip_code, @city, @state
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM geolocation g
    WHERE g.geolocation_zip_code_prefix = c.customer_zip_code_prefix
)
ORDER BY c.customer_id
LIMIT 1;

START TRANSACTION;

INSERT INTO customers (
    customer_id, customer_unique_id, customer_zip_code_prefix,
    customer_city, customer_state, source_file,
    source_ingested_at, source_updated_at, source_row_hash
) VALUES (
    @customer_id, @customer_unique_id, @zip_code,
    @city, @state, @source_file,
    NOW(6), NOW(6), SHA2(CONCAT(@demo_name, '|customer'), 256)
)
ON DUPLICATE KEY UPDATE
    customer_zip_code_prefix = @zip_code,
    customer_city = @city,
    customer_state = @state,
    source_updated_at = NOW(6);

INSERT INTO orders (
    order_id, customer_id, order_status,
    order_purchase_timestamp, order_approved_at,
    order_delivered_carrier_date, order_delivered_customer_date,
    order_estimated_delivery_date, source_file,
    source_ingested_at, source_updated_at, source_row_hash
) VALUES (
    @order_id, @customer_id, 'delivered',
    '2018-08-27 09:00:00', '2018-08-27 09:20:00',
    '2018-08-28 14:00:00', '2018-09-01 16:30:00',
    '2018-09-06 00:00:00', @source_file,
    NOW(6), NOW(6), SHA2(CONCAT(@demo_name, '|order'), 256)
)
ON DUPLICATE KEY UPDATE
    order_status = 'delivered',
    source_updated_at = NOW(6);

INSERT INTO order_items (
    order_id, order_item_id, product_id, seller_id,
    shipping_limit_date, price, freight_value, source_file,
    source_ingested_at, source_updated_at, source_row_hash
) VALUES (
    @order_id, 1, @product_id, @seller_id,
    '2018-08-31 09:20:00', 349.90, 25.00, @source_file,
    NOW(6), NOW(6), SHA2(CONCAT(@demo_name, '|item|1'), 256)
)
ON DUPLICATE KEY UPDATE
    price = 349.90,
    freight_value = 25.00,
    source_updated_at = NOW(6);

INSERT INTO order_payments (
    order_id, payment_sequential, payment_type,
    payment_installments, payment_value, source_file,
    source_ingested_at, source_updated_at, source_row_hash
) VALUES (
    @order_id, 1, 'credit_card',
    3, 374.90, @source_file,
    NOW(6), NOW(6), SHA2(CONCAT(@demo_name, '|payment|1'), 256)
)
ON DUPLICATE KEY UPDATE
    payment_type = 'credit_card',
    payment_installments = 3,
    payment_value = 374.90,
    source_updated_at = NOW(6);

-- review_id bukan unique key di OLTP; hapus hanya review demo agar skrip aman diulang.
DELETE FROM order_reviews
WHERE review_id = @review_id AND order_id = @order_id;

INSERT INTO order_reviews (
    review_id, order_id, review_score,
    review_comment_title, review_comment_message,
    review_creation_date, review_answer_timestamp,
    source_file, source_ingested_at, source_updated_at, source_row_hash
) VALUES (
    @review_id, @order_id, 5,
    'Latihan OLTP ke DWH',
    'Transaksi dummy untuk mempelajari incremental ETL.',
    '2018-09-02 00:00:00', '2018-09-02 10:00:00',
    @source_file, NOW(6), NOW(6),
    SHA2(CONCAT(@demo_name, '|review'), 256)
);

COMMIT;

-- Hasil yang harus terlihat langsung di OLTP.
SELECT
    o.order_id,
    o.order_status,
    o.source_updated_at,
    oi.price,
    oi.freight_value,
    op.payment_value,
    r.review_score
FROM orders o
JOIN order_items oi ON oi.order_id = o.order_id
JOIN order_payments op ON op.order_id = o.order_id
JOIN order_reviews r ON r.order_id = o.order_id
WHERE o.order_id = @order_id;

