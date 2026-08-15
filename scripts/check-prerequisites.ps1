param()

$pythonReady = (Get-Command python -ErrorAction SilentlyContinue) -or (Get-Command py -ErrorAction SilentlyContinue)
"{0,-12} {1}" -f "Python", $(if ($pythonReady) { "Ready" } else { "Missing" })
if (-not $pythonReady) {
    "             Install Python 3.12+ from python.org and enable the launcher or Add Python to PATH."
}

$checks = @(
    @{ Name = "Java"; Command = "java"; Required = $true; Help = "Install a JDK (17 or newer) and add its bin directory to PATH." },
    @{ Name = "javac"; Command = "javac"; Required = $true; Help = "Install a full JDK, not only a Java runtime." },
    @{ Name = "Git"; Command = "git"; Required = $true; Help = "Install Git for Windows and reopen PowerShell." },
    @{ Name = "VS Code"; Command = "code"; Required = $false; Help = "Optional: install VS Code and its shell command." }
)

$missingRequired = -not $pythonReady
foreach ($check in $checks) {
    $found = Get-Command $check.Command -ErrorAction SilentlyContinue
    $status = if ($found) { "Ready" } elseif ($check.Required) { "Missing" } else { "Optional / not found" }
    "{0,-12} {1}" -f $check.Name, $status
    if (-not $found) {
        "             $($check.Help)"
        if ($check.Required) { $missingRequired = $true }
    }
}

$chromeCandidates = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)
$chrome = $chromeCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
"{0,-12} {1}" -f "Chrome", $(if ($chrome) { "Ready" } else { "Missing" })
if (-not $chrome) { "             Install Google Chrome to use LeetCode Accepted detection." }

if ($missingRequired) {
    throw "One or more required prerequisites are missing. Install them explicitly, then rerun setup."
}
