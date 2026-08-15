param()

$ErrorActionPreference = "Stop"
$appRoot = Split-Path -Parent $PSScriptRoot
Set-Location $appRoot

if (-not (Test-Path -LiteralPath ".\venv\Scripts\python.exe")) {
    throw "Virtual environment missing. Run .\scripts\setup.ps1 first."
}

$env:QT_QPA_PLATFORM = "offscreen"
& ".\venv\Scripts\python.exe" -m pytest tests -q
if ($LASTEXITCODE -ne 0) { throw "Python tests failed." }

node --test tests_js\*.test.js
if ($LASTEXITCODE -ne 0) { throw "Chrome extension tests failed." }

Write-Output "All automated tests passed."
