param()
$ErrorActionPreference = "Stop"
$appRoot = Split-Path -Parent $PSScriptRoot
Set-Location $appRoot
$versionSource = Get-Content -LiteralPath (Join-Path $appRoot "app\version.py") -Raw
if ($versionSource -notmatch 'VERSION\s*=\s*"([^"]+)"') {
    throw "Could not read VERSION from app\version.py"
}
$appVersion = $Matches[1]
$buildCommit = (git rev-parse HEAD).Trim()
$trackedChanges = git status --porcelain --untracked-files=no
$buildDirty = [bool]$trackedChanges
$buildTimestamp = (Get-Date).ToUniversalTime().ToString("o")
$tempRoot = [System.IO.Path]::GetTempPath()
$buildMetadataDir = Join-Path $tempRoot "dsa-accountability-build-$PID"
if (-not ([System.IO.Path]::GetFullPath($buildMetadataDir)).StartsWith([System.IO.Path]::GetFullPath($tempRoot), [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing unsafe build metadata path: $buildMetadataDir"
}
New-Item -ItemType Directory -Path $buildMetadataDir -ErrorAction Stop | Out-Null
$buildInfoPath = Join-Path $buildMetadataDir "build_info.json"
$versionInfoPath = Join-Path $buildMetadataDir "version_info.txt"

@{
    version = $appVersion
    commit = $buildCommit
    built_at = $buildTimestamp
    dirty = $buildDirty
} | ConvertTo-Json | Set-Content -LiteralPath $buildInfoPath -Encoding UTF8

$versionInfo = @"
VSVersionInfo(
  ffi=FixedFileInfo(filevers=(1, 1, 0, 0), prodvers=(1, 1, 0, 0), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'DSA Accountability'),
      StringStruct('FileDescription', 'DSA Accountability'),
      StringStruct('FileVersion', '$appVersion'),
      StringStruct('InternalName', 'DSAAccountability'),
      StringStruct('OriginalFilename', 'DSAAccountability.exe'),
      StringStruct('ProductName', 'DSA Accountability'),
      StringStruct('ProductVersion', '$appVersion')
    ])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"@
Set-Content -LiteralPath $versionInfoPath -Value $versionInfo -Encoding UTF8

Write-Output "Building DSAAccountability.exe with PyInstaller..."

try {
    & ".\venv\Scripts\python.exe" -m PyInstaller `
        --name DSAAccountability `
        --windowed `
        --noconfirm `
        --clean `
        --paths . `
        --add-data "curriculum;curriculum" `
        --add-data "app\migrations;app\migrations" `
        --add-data "$buildInfoPath;." `
        --version-file "$versionInfoPath" `
        --hidden-import zoneinfo `
        --collect-data tzdata `
        app\main.py
} finally {
    if (Test-Path -LiteralPath $buildMetadataDir) {
        Remove-Item -LiteralPath $buildMetadataDir -Recurse -Force
    }
}

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed."
    exit 1
}

Write-Output ""
Write-Output "Build complete: dist\DSAAccountability\DSAAccountability.exe"
