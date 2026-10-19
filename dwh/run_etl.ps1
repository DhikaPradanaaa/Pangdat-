param(
    [string]$SourceDir = "D:\Pangdat\output\olist_data_quality_final\clean",
    [string]$OutputDir = "D:\Pangdat\output\olist_dwh",
    [switch]$IncludeErrors
)

$arguments = @(
    "D:\Pangdat\scripts\build_olist_dwh.py",
    "--source-dir", $SourceDir,
    "--output-dir", $OutputDir,
    "--schema", "D:\Pangdat\dwh\schema.sql"
)

if ($IncludeErrors) {
    $arguments += "--include-errors"
}

python @arguments
