# Olist OLTP → Staging → DWH → Dashboard

Proyek ini menjalankan alur data end-to-end pada MySQL 8 milik Laragon. SQLyog dapat digunakan untuk melihat ketiga database, menjalankan query, dan memeriksa hasil ETL.

## Arsitektur

```text
CSV asli
  → olist_oltp
  → olist_staging.stg_raw_*
  → profiling, data quality, cleansing
  → olist_staging.stg_clean_* + quarantine
  → olist_dwh (star schema)
  → data mart
  → dashboard Streamlit
```

Database:

- `olist_oltp`: salinan sumber transaksi sebelum dibersihkan.
- `olist_staging`: raw staging, clean staging, batch, watermark, issue, dan reject.
- `olist_dwh`: dimensi, fakta, event perjalanan order, dan data mart.

## Menjalankan initial load

Pastikan MySQL Laragon aktif, kemudian:

```powershell
python D:\Pangdat\olist_pipeline\src\seed_oltp.py
python D:\Pangdat\olist_pipeline\src\run_pipeline.py --mode full
```

## Menjalankan incremental load

```powershell
python D:\Pangdat\olist_pipeline\src\simulate_oltp_feed.py --touch-latest 25
python D:\Pangdat\olist_pipeline\src\run_pipeline.py --mode incremental
```

Incremental mode hanya menyalin perubahan baru ke raw staging berdasarkan `source_updated_at`. Untuk menjaga hasil akademik tetap deterministik pada ukuran dataset ini, tahap conformance dan publikasi DWH membangun ulang snapshot bersih secara idempotent. Watermark hanya maju setelah seluruh proses dan validasi berhasil.

## Dashboard

```powershell
powershell -ExecutionPolicy Bypass -File D:\Pangdat\olist_pipeline\dashboard\run_dashboard.ps1
```

Buka `http://127.0.0.1:8501`.

Dashboard hanya membaca `olist_dwh` serta tabel audit terpilih. Dashboard tidak membaca OLTP.

## Scheduler

Daftarkan ETL harian pukul 01.00:

```powershell
powershell -ExecutionPolicy Bypass -File D:\Pangdat\olist_pipeline\scheduler\register_task.ps1
```

Scheduled task menjalankan `scheduler/run_daily.ps1`.

## Melihat melalui SQLyog

1. Buka Laragon dan klik **Start All**.
2. Di SQLyog buat atau buka koneksi dengan host `127.0.0.1`, port `3306`, user `root`, dan password kosong (konfigurasi Laragon lokal saat proyek ini dibuat).
3. Klik **Connect**, lalu klik kanan Object Browser dan pilih **Refresh Object Browser**.

Database yang harus terlihat:

1. `olist_oltp`
2. `olist_staging`
3. `olist_dwh`

Query awal:

```sql
SELECT * FROM olist_staging.etl_batch ORDER BY started_at DESC;
SELECT * FROM olist_dwh.mart_monthly_sales;
SELECT * FROM olist_dwh.mart_data_quality ORDER BY completed_at DESC;
```

Kumpulan query pemeriksaan yang lebih lengkap tersedia pada `sql/queries_for_sqlyog.sql`. Buka file tersebut melalui **File → Open**, sorot query yang ingin dijalankan, kemudian tekan `F9`.

Tabel utama yang dapat dibuka tanpa menulis query:

- OLTP: `olist_oltp.orders`, `order_items`, `order_payments`, dan tabel transaksi lainnya.
- Staging: `olist_staging.stg_raw_*`, `stg_clean_*`, `dq_rule_result`, `dq_issue_detail`, `etl_reject`, dan `etl_batch`.
- DWH: `olist_dwh.dim_*`, `fact_*`, serta view `mart_*`.

Untuk melihat isi tabel, klik kanan nama tabel di SQLyog lalu pilih **Open Table → Return All Rows**. Untuk tabel besar, gunakan tab **Data** atau query dengan `LIMIT 100` agar SQLyog tetap ringan.

## Data quality

Aturan mencakup accuracy, domain integrity, data type, consistency, redundancy, completeness, duplication, business rules, structural definiteness, anomaly, clarity, timeliness, dan referential integrity.

Kebijakan pemuatan:

- `valid`, `corrected`, dan `warning` dimuat ke DWH.
- `error` dicatat dalam `olist_staging.etl_reject`.
- Setiap detail masalah tersedia di `olist_staging.dq_issue_detail`.

## Pengujian

```powershell
python -m pytest D:\Pangdat\olist_pipeline\tests -q
```

Pengujian memeriksa initial load OLTP, batch terakhir, validasi DWH, grain fakta, dan ketersediaan data mart.

## Pemulihan

Versi DWH sebelum implementasi pipeline disimpan di:

```text
D:\Pangdat\olist_pipeline\backups\olist_dwh_before_pipeline.sql
```
