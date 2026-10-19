# Olist Data Warehouse untuk MySQL 8

## Cara impor menggunakan MySQL Workbench

1. Buka MySQL Workbench dan hubungkan ke MySQL Server.
2. Pilih **Server > Data Import**.
3. Pilih **Import from Self-Contained File**.
4. Pilih `olist_dwh_mysql.sql`.
5. Klik **Start Import**.
6. Refresh panel **Schemas**, lalu buka schema `olist_dwh`.

Dump bersifat full refresh: schema `olist_dwh` akan dibuat jika belum ada, kemudian tabel dan view dengan nama yang sama akan dibuat ulang. Jangan jalankan dump pada schema yang berisi perubahan manual yang ingin dipertahankan.

## Cara melihat data

Di panel **Schemas**, buka `olist_dwh > Tables`. Klik kanan tabel dan pilih **Select Rows - Limit 1000**.

Tabel fakta utama:

- `fact_order`
- `fact_sales`
- `fact_payment`
- `fact_review`

Tabel dimensi:

- `dim_date`
- `dim_geolocation`
- `dim_customer`
- `dim_seller`
- `dim_product`

View analitik:

- `vw_order_summary`
- `vw_monthly_sales`
- `vw_product_sales`

Jalankan `validation_mysql.sql` setelah impor. Nilai `failed_validation_count` harus `0`.
