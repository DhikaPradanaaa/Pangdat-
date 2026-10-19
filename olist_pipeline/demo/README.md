# Latihan OLTP ke DWH

Prasyarat: Laragon/MySQL aktif dan initial full load sudah pernah berhasil.

1. Buka `01_insert_oltp.sql` di SQLyog, lalu jalankan seluruh isinya dengan `F9`.
2. Buka `03_verify_oltp_to_dwh.sql`. Sebelum ETL, bagian OLTP menghasilkan satu baris dan bagian DWH belum menghasilkan baris.
3. Dari root repository, jalankan:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\olist_pipeline\demo\02_run_incremental_etl.ps1
   ```

4. Jalankan lagi `03_verify_oltp_to_dwh.sql` di SQLyog.

Hasil yang diharapkan setelah ETL:

- Batch terbaru: `load_mode = incremental`, `status = SUCCESS`.
- Raw staging memuat order demo pada batch tersebut.
- DWH memuat satu order, item, pembayaran, dan review baru.
- `line_total = 374.90`, `payment_value = 374.90`, `review_score = 5`.
- `dq_status = valid` dan query quarantine tidak menghasilkan baris.

File insert aman dijalankan ulang: data demo yang sama diperbarui dan `source_updated_at` dibuat baru, sehingga dapat dipakai untuk mengulangi latihan incremental.

