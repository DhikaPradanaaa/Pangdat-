$ErrorActionPreference = "Stop"
$project = Split-Path $PSScriptRoot -Parent

python (Join-Path $project "src\run_pipeline.py") --mode incremental
if ($LASTEXITCODE -ne 0) {
    throw "Incremental ETL gagal. Periksa output error di atas."
}

Write-Host "ETL SUCCESS. Jalankan demo\03_verify_oltp_to_dwh.sql di SQLyog."

