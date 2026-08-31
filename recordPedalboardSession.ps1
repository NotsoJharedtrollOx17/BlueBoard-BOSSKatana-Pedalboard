param(
    [switch]$Active,
    [double]$DurationMinutes,
    [string]$LogDirectory,
    [switch]$Debug,
    [switch]$LedFeedback,
    [string]$Name,
    [string]$Address,
    [double]$ScanTimeout
)
$ErrorActionPreference = "Stop"
$repoRoot = $PSScriptRoot
$pythonExe = Join-Path $repoRoot "python\.venv\Scripts\python.exe"
$configFile = Join-Path $repoRoot "python\config\katana-pedalboard.local.json"

if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
    throw "Python environment not found. Run .\setupPedalboard.ps1 first."
}
if (-not (Test-Path -LiteralPath $configFile -PathType Leaf)) {
    throw "Local pedalboard configuration not found. Run .\onboardPedalboard.ps1 first."
}
if ($PSBoundParameters.ContainsKey("DurationMinutes") -and $DurationMinutes -le 0) {
    throw "-DurationMinutes must be positive."
}
if (-not $LogDirectory) {
    $LogDirectory = Join-Path $repoRoot "logs\pedalboard-sessions"
}

New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$logFile = Join-Path $LogDirectory "pedalboard-session-$timestamp.jsonl"
$sessionArgs = @("run", "--config", $configFile, "--json-logs", "--log-file", $logFile)
if ($Active) { $sessionArgs += "--execute-actions" }
if ($Debug) { $sessionArgs += "--debug" }
if ($LedFeedback) { $sessionArgs += "--led-feedback" }
if ($PSBoundParameters.ContainsKey("Name")) { $sessionArgs += @("--name", $Name) }
if ($PSBoundParameters.ContainsKey("Address")) { $sessionArgs += @("--address", $Address) }
if ($PSBoundParameters.ContainsKey("ScanTimeout")) { $sessionArgs += @("--scan-timeout", $ScanTimeout) }
if ($PSBoundParameters.ContainsKey("DurationMinutes")) {
    $durationSeconds = $DurationMinutes * 60
    $sessionArgs += @("--duration-seconds", $durationSeconds.ToString([Globalization.CultureInfo]::InvariantCulture))
}

$mode = if ($Active) { "ACTIVE: configured Katana actions are enabled." } else { "DRY RUN: no Katana actions will run." }
Write-Host "Recording a pedalboard session. $mode"
if ($PSBoundParameters.ContainsKey("DurationMinutes")) {
    Write-Host "The session will stop cleanly after $DurationMinutes minute(s)."
} else {
    Write-Host "Press Ctrl+C to stop the session cleanly."
}
Write-Host "Structured log: $logFile"
& $pythonExe -m blueboard_macro_handler @sessionArgs
$exitCode = $LASTEXITCODE
Write-Host "Session log retained at: $logFile"
exit $exitCode
