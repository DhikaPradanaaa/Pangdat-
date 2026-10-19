-- 1. Penjualan bulanan
SELECT *
FROM vw_monthly_sales
ORDER BY year_number, month_number;

-- 2. Sepuluh kategori dengan nilai penjualan tertinggi
SELECT category_name_english, order_count, item_count, gross_sales
FROM vw_product_sales
ORDER BY gross_sales DESC
LIMIT 10;

-- 3. Persentase keterlambatan pengiriman per bulan pembelian
SELECT d.year_number,
       d.month_number,
       COUNT(*) AS delivered_orders,
       SUM(o.is_late) AS late_orders,
       ROUND(100.0 * SUM(o.is_late) / COUNT(*), 2) AS late_order_percent
FROM fact_order o
JOIN dim_date d ON d.date_key = o.purchase_date_key
WHERE o.is_delivered = 1
GROUP BY d.year_number, d.month_number
ORDER BY d.year_number, d.month_number;

-- 4. Nilai pembayaran menurut jenis pembayaran
SELECT payment_type,
       COUNT(DISTINCT order_key) AS order_count,
       COUNT(*) AS payment_count,
       SUM(payment_value) AS payment_value
FROM fact_payment
GROUP BY payment_type
ORDER BY payment_value DESC;

-- 5. Hubungan keterlambatan dengan skor ulasan
SELECT o.is_late,
       COUNT(*) AS review_count,
       ROUND(AVG(r.review_score), 2) AS average_review_score
FROM fact_review r
JOIN fact_order o ON o.order_key = r.order_key
WHERE o.is_delivered = 1
GROUP BY o.is_late;

-- Gunakan vw_order_summary bila membutuhkan item, pembayaran, dan ulasan
-- dalam satu hasil. View tersebut sudah mengagregasikan masing-masing fakta
-- agar nilai pembayaran tidak berlipat karena banyak item.
