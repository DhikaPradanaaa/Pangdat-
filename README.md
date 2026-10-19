# Pangdat — Olist Data Warehouse Pipeline

Proyek pangkalan data yang mengimplementasikan alur lengkap:

```text
OLTP MySQL → raw staging → data quality & cleansing → star-schema DWH
→ data mart → dashboard Streamlit → scheduler incremental harian
```

Implementasi utama berada di [`olist_pipeline/`](olist_pipeline/). Petunjuk instalasi, koneksi Laragon/SQLyog, menjalankan ETL, dashboard, scheduler, dan pengujian tersedia di [`olist_pipeline/README.md`](olist_pipeline/README.md).

## Isi repository

- `olist_pipeline/` — pipeline end-to-end, SQL, dashboard, scheduler, test, dan dokumentasi arsitektur.
- `scripts/` — skrip data quality, pembangunan DWH, dan ekspor MySQL.
- `dwh/` — skema star schema dan contoh analisis SQL.
- `mysql/` — skema serta validasi untuk MySQL 8/Laragon.
- `shared_packages/` — dataset asli dan paket hasil data quality/DWH yang siap dibagikan.

Dataset asli dan hasil build yang aman dibagikan tersedia sebagai arsip terkompresi di [`shared_packages/`](shared_packages/). File runtime yang berulang, log lokal, kredensial, private key, cache, dan dependency hasil instalasi tetap dikecualikan.
