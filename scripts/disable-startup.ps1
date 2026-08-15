param()
$ErrorActionPreference = "Stop"
$startupFolder = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
$shortcutPath = Join-Path $startupFolder "DSAAccountability.lnk"

$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
if (Get-ItemProperty -Path $runKey -Name "DSAAccountability" -ErrorAction SilentlyContinue) {
    Remove-ItemProperty -Path $runKey -Name "DSAAccountability" -Force
    Write-Output "Removed legacy Run-key entry."
}
try { schtasks /delete /tn "DSAAccountability" /f | Out-Null } catch {}

if (Test-Path $shortcutPath) {
    Remove-Item $shortcutPath -Force
    Write-Output "Startup DISABLED (shortcut removed)."
} else {
    Write-Output "Startup was already disabled (no shortcut found)."
}
