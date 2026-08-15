param()
$ErrorActionPreference = "Stop"
$appRoot = Split-Path -Parent $PSScriptRoot
$exePath = Join-Path $appRoot "dist\DSAAccountability\DSAAccountability.exe"
$startupFolder = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
$shortcutPath = Join-Path $startupFolder "DSAAccountability.lnk"

if (-not (Test-Path $exePath)) {
    Write-Error "Packaged exe not found at $exePath. Run .\scripts\build.ps1 first."
    exit 1
}

# Clean up legacy Run-key / Task Scheduler entries from earlier versions.
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
if (Get-ItemProperty -Path $runKey -Name "DSAAccountability" -ErrorAction SilentlyContinue) {
    Remove-ItemProperty -Path $runKey -Name "DSAAccountability" -Force
}
try { schtasks /delete /tn "DSAAccountability" /f | Out-Null } catch {}

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($shortcutPath)
$Shortcut.TargetPath = $exePath
# No --minimized: the always-on-top overlay must be visible immediately
# at logon, not hidden in the tray until manually restored. Must be set
# explicitly (not just omitted) -- CreateShortcut() loads an existing
# .lnk's properties, so any stale Arguments value from a previous version
# would otherwise survive unchanged into the new shortcut.
$Shortcut.Arguments = ""
$Shortcut.WorkingDirectory = Split-Path $exePath -Parent
$Shortcut.Save()

Write-Output "Startup ENABLED via Startup-folder shortcut:"
Write-Output "  $shortcutPath -> $exePath"
