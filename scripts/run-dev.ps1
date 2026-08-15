param()
$ErrorActionPreference = "Stop"
$appRoot = Split-Path -Parent $PSScriptRoot
Set-Location $appRoot
& ".\venv\Scripts\python.exe" "app\main.py"
