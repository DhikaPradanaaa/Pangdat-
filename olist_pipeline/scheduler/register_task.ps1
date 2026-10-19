$taskName = "OlistDailyETL"
$script = "D:\Pangdat\olist_pipeline\scheduler\run_daily.ps1"
$action = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$script`""

schtasks.exe /Create /TN $taskName /TR $action /SC DAILY /ST 01:00 /F
if ($LASTEXITCODE -ne 0) {
    throw "Gagal mendaftarkan scheduled task $taskName"
}

Write-Host "Scheduled task $taskName aktif setiap hari pukul 01:00."
