param(
    [switch]$RunTests,
    [switch]$Build
)

$ErrorActionPreference = "Stop"
$appRoot = Split-Path -Parent $PSScriptRoot
Set-Location $appRoot

& "$PSScriptRoot\check-prerequisites.ps1"

$python = Get-Command py -ErrorAction SilentlyContinue
if ($python) {
    $pythonCommand = @("py", "-3")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCommand = @("python")
} else {
    throw "Python 3.12 or newer is required. Install Python, reopen PowerShell, and rerun this script."
}

if (-not (Test-Path -LiteralPath ".\venv\Scripts\python.exe")) {
    Write-Output "Creating project virtual environment..."
    if ($pythonCommand[0] -eq "py") {
        & py -3 -m venv venv
    } else {
        & python -m venv venv
    }
    if ($LASTEXITCODE -ne 0) { throw "Could not create the virtual environment." }
}

Write-Output "Installing project dependencies into .\venv..."
& ".\venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\venv\Scripts\python.exe" -m pip install -r requirements.txt

Write-Output "Regenerating bundled curriculum and extension icons..."
& ".\venv\Scripts\python.exe" curriculum\build_schedule.py
& ".\venv\Scripts\python.exe" curriculum\gen_curriculum_md.py
& ".\venv\Scripts\python.exe" scripts\gen_icons.py

if ($RunTests) {
    & "$PSScriptRoot\test.ps1"
}

if ($Build) {
    & "$PSScriptRoot\build.ps1"
}

Write-Output ""
Write-Output "Setup complete."
Write-Output "Run from source: .\scripts\run-dev.ps1"
Write-Output "Build executable: .\scripts\build.ps1"
Write-Output "Chrome remains a manual step: load the chrome-extension folder as an unpacked extension."
