SET @order_id = MD5('lab_oltp_dwh_20261019_001_order');

-- A. Data transaksi sumber di OLTP.
SELECT
    'OLTP' AS layer_name,
    o.order_id,
    o.order_status,
    o.order_purchase_timestamp,
    oi.price,
    oi.freight_value,
    op.payment_value,
    r.review_score,
    o.source_updated_at
FROM olist_oltp.orders o
JOIN olist_oltp.order_items oi ON oi.order_id = o.order_id
JOIN olist_oltp.order_payments op ON op.order_id = o.order_id
JOIN olist_oltp.order_reviews r ON r.order_id = o.order_id
WHERE o.order_id = @order_id;

-- B. Batch incremental yang memproses perubahan terbaru.
SELECT
    batch_id, load_mode, status,
    source_rows, clean_rows, rejected_rows,
    watermark_start, watermark_end,
    started_at, completed_at
FROM olist_staging.etl_batch
ORDER BY started_at DESC
LIMIT 1;

-- C. Baris order yang diekstrak ke raw staging.
SELECT batch_id, extracted_at, order_id, order_status, source_updated_at
FROM olist_staging.stg_raw_orders
WHERE order_id = @order_id
ORDER BY extracted_at DESC;

-- D. Hasil akhir transaksi di DWH.
SELECT
    'DWH' AS layer_name,
    fo.order_id,
    fo.order_status,
    fo.purchase_timestamp,
    dc.city AS customer_city,
    dc.state AS customer_state,
    dp.category_name AS product_category_name,
    ds.city AS seller_city,
    fs.price,
    fs.freight_value,
    fs.line_total,
    fp.payment_type,
    fp.payment_installments,
    fp.payment_value,
    fr.review_score,
    fo.delivery_days,
    fo.delay_days,
    fo.is_late,
    fo.dq_status
FROM olist_dwh.fact_order fo
JOIN olist_dwh.dim_customer dc ON dc.customer_key = fo.customer_key
JOIN olist_dwh.fact_sales fs ON fs.order_key = fo.order_key
JOIN olist_dwh.dim_product dp ON dp.product_key = fs.product_key
JOIN olist_dwh.dim_seller ds ON ds.seller_key = fs.seller_key
JOIN olist_dwh.fact_payment fp ON fp.order_key = fo.order_key
JOIN olist_dwh.fact_review fr ON fr.order_key = fo.order_key
WHERE fo.order_id = @order_id;

-- E. Pastikan transaksi demo tidak masuk quarantine.
SELECT *
FROM olist_staging.etl_reject
WHERE business_key = @order_id
ORDER BY reject_id DESC;

