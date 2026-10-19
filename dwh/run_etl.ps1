param(
    [string]$SourceDir = (Join-Path (Split-Path $PSScriptRoot -Parent) "output\olist_data_quality_final\clean"),
    [string]$OutputDir = (Join-Path (Split-Path $PSScriptRoot -Parent) "output\olist_dwh"),
    [switch]$IncludeErrors
)

$workspace = Split-Path $PSScriptRoot -Parent
$arguments = @(
    (Join-Path $workspace "scripts\build_olist_dwh.py"),
    "--source-dir", $SourceDir,
    "--output-dir", $OutputDir,
    "--schema", (Join-Path $workspace "dwh\schema.sql")
)

if ($IncludeErrors) {
    $arguments += "--include-errors"
}

python @arguments
