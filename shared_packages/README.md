# Paket data dan DWH

Semua data di folder ini adalah dataset dummy Olist dan hasil pemrosesannya.

| File | Isi |
|---|---|
| `olist_original_dataset.zip` | Sembilan CSV OLTP asli, sebelum pembersihan. |
| `olist_data_quality_final.zip` | Data raw, clean, quarantine, metadata, dan laporan kualitas. |
| `olist_dwh_package.zip` | SQLite DWH, skema, validasi, dan contoh analisis. |
| `olist_dwh_mysql_package.zip` | Dump MySQL 8, skema, validasi, dan contoh analisis. |
| `olist_pipeline_project.zip` | Salinan ringkas kode pipeline. |

## Menjalankan pipeline dari dataset asli

Dari root repository di PowerShell:

```powershell
New-Item -ItemType Directory -Force .\output\olist_data_quality_final\raw
Expand-Archive .\shared_packages\olist_original_dataset.zip .\output\olist_data_quality_final\raw -Force
Copy-Item .\olist_pipeline\.env.example .\olist_pipeline\.env
python .\olist_pipeline\src\seed_oltp.py
python .\olist_pipeline\src\run_pipeline.py --mode full
```

Laragon/MySQL harus aktif. Sesuaikan `.env` apabila user atau password MySQL berbeda. Lokasi `mysql.exe` dapat diubah melalui variabel `MYSQL_CLIENT` di `.env`.
