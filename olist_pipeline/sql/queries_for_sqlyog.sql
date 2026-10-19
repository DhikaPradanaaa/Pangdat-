-- Jalankan bagian ini setelah memilih koneksi Laragon di SQLyog.

-- 1. Status batch ETL
SELECT *
FROM olist_staging.etl_batch
ORDER BY started_at DESC;

-- 2. Watermark setiap tabel sumber
SELECT *
FROM olist_staging.etl_watermark
ORDER BY source_table;

-- 3. Penjualan bulanan
SELECT *
FROM olist_dwh.mart_monthly_sales
ORDER BY year_number, month_number;

-- 4. Kategori teratas
SELECT *
FROM olist_dwh.mart_category_performance
ORDER BY gross_sales DESC
LIMIT 20;

-- 5. Keterlambatan pengiriman
SELECT *
FROM olist_dwh.mart_delivery_performance
ORDER BY year_number, month_number;

-- 6. Aturan kualitas dengan masalah terbanyak
SELECT rule_id,dimension_name,severity,detected_count,corrected_count,open_count,quarantined_count,result
FROM olist_staging.dq_rule_result
WHERE batch_id=(SELECT batch_id FROM olist_staging.etl_batch ORDER BY started_at DESC LIMIT 1)
ORDER BY detected_count DESC;

-- 7. Demo incremental: jalankan sekarang untuk melihat transaksi di OLTP
SELECT
    o.order_id,
    o.order_status,
    o.source_updated_at,
    oi.price,
    oi.freight_value,
    op.payment_value,
    r.review_score
FROM olist_oltp.orders o
JOIN olist_oltp.order_items oi ON oi.order_id = o.order_id
JOIN olist_oltp.order_payments op ON op.order_id = o.order_id
JOIN olist_oltp.order_reviews r ON r.order_id = o.order_id
WHERE o.order_id = 'demo20261013order000000000000001';

-- 8. Demo incremental: jalankan setelah scheduler selesai besok
SELECT
    fo.order_id,
    fo.order_status,
    fo.purchase_timestamp,
    fs.price,
    fs.freight_value,
    fs.line_total,
    fp.payment_value,
    fr.review_score,
    fo.dq_status
FROM olist_dwh.fact_order fo
JOIN olist_dwh.fact_sales fs ON fs.order_key = fo.order_key
JOIN olist_dwh.fact_payment fp ON fp.order_key = fo.order_key
JOIN olist_dwh.fact_review fr ON fr.order_key = fo.order_key
WHERE fo.order_id = 'demo20261013order000000000000001';
