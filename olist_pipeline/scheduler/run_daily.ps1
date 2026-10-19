$ErrorActionPreference = "Stop"
$project = "D:\Pangdat\olist_pipeline"
$logDir = Join-Path $project "logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$log = Join-Path $logDir "scheduled-$stamp.log"

python (Join-Path $project "src\run_pipeline.py") --mode incremental *>&1 | Tee-Object -FilePath $log
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
