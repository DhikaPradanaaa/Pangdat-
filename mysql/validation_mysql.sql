USE olist_dwh;

-- Semua nilai harus sama dengan expected_value dan tidak ada status FAIL.
SELECT check_name, status, expected_value, actual_value
FROM etl_validation_result
ORDER BY validation_key;

SELECT COUNT(*) AS failed_validation_count
FROM etl_validation_result
WHERE status = 'FAIL';

SELECT
    (SELECT COUNT(*) FROM dim_date) AS dim_date_rows,
    (SELECT COUNT(*) FROM dim_geolocation) AS dim_geolocation_rows,
    (SELECT COUNT(*) FROM dim_customer) AS dim_customer_rows,
    (SELECT COUNT(*) FROM dim_seller) AS dim_seller_rows,
    (SELECT COUNT(*) FROM dim_product) AS dim_product_rows,
    (SELECT COUNT(*) FROM fact_order) AS fact_order_rows,
    (SELECT COUNT(*) FROM fact_sales) AS fact_sales_rows,
    (SELECT COUNT(*) FROM fact_payment) AS fact_payment_rows,
    (SELECT COUNT(*) FROM fact_review) AS fact_review_rows;

SELECT ROUND(SUM(line_total), 2) AS gross_sales
FROM fact_sales;

SELECT ROUND(SUM(payment_value), 2) AS payment_value
FROM fact_payment;

SELECT *
FROM vw_monthly_sales
ORDER BY year_number, month_number;
