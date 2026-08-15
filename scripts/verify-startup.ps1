param()
$startupFolder = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
$shortcutPath = Join-Path $startupFolder "DSAAccountability.lnk"

if (Test-Path $shortcutPath) {
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut($shortcutPath)
    Write-Output "Startup is ENABLED via Startup-folder shortcut."
    Write-Output "  Shortcut: $shortcutPath"
    Write-Output "  Target:   $($Shortcut.TargetPath) $($Shortcut.Arguments)"
    if (-not (Test-Path $Shortcut.TargetPath)) {
        Write-Output "  WARNING: target exe does not exist -- rebuild and re-run enable-startup.ps1"
    }
} else {
    Write-Output "Startup is DISABLED (no shortcut found at $shortcutPath)."
}

$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$legacy = Get-ItemProperty -Path $runKey -Name "DSAAccountability" -ErrorAction SilentlyContinue
if ($legacy) {
    Write-Output ""
    Write-Output "WARNING: a legacy Run-key entry also exists and should be removed:"
    Write-Output "  $($legacy.DSAAccountability)"
}
$taskCheck = schtasks /query /tn "DSAAccountability" 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Output ""
    Write-Output "WARNING: a legacy Scheduled Task also exists and should be removed."
}
