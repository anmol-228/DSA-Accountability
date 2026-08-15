param()

$ErrorActionPreference = "Stop"
$failures = @()

$forbiddenFiles = git ls-files | Select-String -Pattern '(?i)(\.sqlite($|-)|\.sqlite-wal$|\.sqlite-shm$|\.env$|\.log$|CODEX_|HANDOFF|FINAL_REPAIR|PROJECT_STATE|docs/archive/)'
if ($forbiddenFiles) {
    $failures += "Forbidden private/generated tracked paths:`n$($forbiddenFiles -join "`n")"
}

$personalMatches = git grep -n -I -E 'W:\\|C:\\Users\\|Anmol Trivedi|b2399305' -- . ':(exclude)LICENSE' ':(exclude)scripts/check-public-safety.ps1' ':(exclude)scripts/validate-docs.py' 2>$null
if ($LASTEXITCODE -eq 0) {
    $failures += "Machine-specific/private content:`n$($personalMatches -join "`n")"
} elseif ($LASTEXITCODE -ne 1) {
    throw "git grep failed while checking personal paths."
}

$secretMatches = git grep -n -I -E '(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY|Authorization:[[:space:]]*(Bearer|Basic)[[:space:]]+[A-Za-z0-9._~+/=-]+)' -- . 2>$null
if ($LASTEXITCODE -eq 0) {
    $failures += "Credential-like content:`n$($secretMatches -join "`n")"
} elseif ($LASTEXITCODE -ne 1) {
    throw "git grep failed while checking credential patterns."
}

if ($failures.Count -gt 0) {
    $failures | ForEach-Object { Write-Error $_ }
    throw "Public safety check failed."
}

Write-Output "Public safety check passed: no forbidden tracked artifacts, personal paths, or credential patterns."
exit 0
