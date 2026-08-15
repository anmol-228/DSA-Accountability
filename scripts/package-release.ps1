param(
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$appRoot = Split-Path -Parent $PSScriptRoot
Set-Location $appRoot
$versionSource = Get-Content -LiteralPath (Join-Path $appRoot "app\version.py") -Raw
if ($versionSource -notmatch 'VERSION\s*=\s*"([^"]+)"') {
    throw "Could not read VERSION from app\version.py"
}
$version = $Matches[1]

if (-not $SkipBuild) {
    & "$PSScriptRoot\build.ps1"
}

$distApp = Join-Path $appRoot "dist\DSAAccountability"
if (-not (Test-Path -LiteralPath (Join-Path $distApp "DSAAccountability.exe"))) {
    throw "Packaged app missing. Run .\scripts\build.ps1 first."
}

$releaseRoot = Join-Path $appRoot "release"
$stage = Join-Path $releaseRoot "DSAAccountability-Windows-x64-v$version"
$zip = "$stage.zip"
if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
New-Item -ItemType Directory -Path $stage -Force | Out-Null

Copy-Item -Path "$distApp\*" -Destination $stage -Recurse -Force
Copy-Item -LiteralPath "$appRoot\chrome-extension" -Destination "$stage\chrome-extension" -Recurse -Force
Copy-Item -LiteralPath "$appRoot\docs\PREBUILT_QUICK_START.md" -Destination "$stage\README.txt"
Copy-Item -LiteralPath "$appRoot\LICENSE" -Destination "$stage\LICENSE.txt"

Compress-Archive -Path "$stage\*" -DestinationPath $zip -CompressionLevel Optimal
Write-Output "Release ZIP: $zip"
Get-FileHash -Algorithm SHA256 -LiteralPath $zip
