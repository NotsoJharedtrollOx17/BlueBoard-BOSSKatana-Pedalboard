param(
    [switch]$Dev,
    [string]$PythonExe,
    [switch]$RefreshEnvironment,
    [string]$Output,
    [ValidateSet("katana100", "katana100MkII")]
    [string]$Model,
    [ValidateSet("panel-first", "channels-1-2")]
    [string]$Layout,
    [int]$MidiChannel,
    [string]$Firmware,
    [string]$Name,
    [string]$Address,
    [double]$ScanTimeout,
    [switch]$NonInteractive,
    [switch]$AcceptProfileStateDefaults,
    [switch]$Force,
    [switch]$VerifyExisting,
    [switch]$Debug,
    [switch]$JsonLogs,
    [string]$LogFile
)
$ErrorActionPreference = "Stop"
$repoRoot = $PSScriptRoot
$venvPythonExe = Join-Path $repoRoot "python\.venv\Scripts\python.exe"
$configFile = Join-Path $repoRoot "python\config\katana-pedalboard.local.json"
$requiredVersion = "0.4.0"

function Test-OnboardingEnvironment([string]$Candidate) {
    if (-not (Test-Path -LiteralPath $Candidate -PathType Leaf)) { return $false }
    try {
        $status = & $Candidate -c "import sys; import blueboard_macro_handler as package; print(int((3, 10) <= sys.version_info[:2] < (3, 13) and package.__version__ == '$requiredVersion'))"
        return $LASTEXITCODE -eq 0 -and $status.Trim() -eq "1"
    } catch {
        return $false
    }
}

$environmentReady = Test-OnboardingEnvironment $venvPythonExe
if ($RefreshEnvironment -or -not $environmentReady) {
    $setupArgs = @()
    if ($Dev) { $setupArgs += "-Dev" }
    if ($PythonExe) { $setupArgs += @("-PythonExe", $PythonExe) }
    Write-Host "Preparing the local pedalboard environment..."
    & (Join-Path $repoRoot "setupPedalboard.ps1") @setupArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Pedalboard setup failed with exit code $LASTEXITCODE."
    }
    if (-not (Test-OnboardingEnvironment $venvPythonExe)) {
        throw "Setup completed, but the local v0.4.0 environment is not ready."
    }
} else {
    Write-Host "Reusing the compatible local v0.4.0 environment."
}

$profileOptions = @("Output", "Model", "Layout", "MidiChannel", "Firmware", "Name", "Address", "ScanTimeout", "NonInteractive", "AcceptProfileStateDefaults")
$hasProfileOptions = @($profileOptions | Where-Object { $PSBoundParameters.ContainsKey($_) }).Count -gt 0
if ($VerifyExisting -and $Force) {
    throw "-VerifyExisting cannot be combined with -Force."
}
if ($VerifyExisting -and -not (Test-Path -LiteralPath $configFile -PathType Leaf)) {
    throw "No saved profile exists at $configFile. Remove -VerifyExisting to create one."
}
if ((Test-Path -LiteralPath $configFile -PathType Leaf) -and -not $Force -and $hasProfileOptions -and -not $VerifyExisting) {
    throw "A saved profile already exists. Use -VerifyExisting to check it, or add -Force to replace it with the supplied options."
}

$onboardArgs = @("onboard", "--config", $configFile)
if ($VerifyExisting -or ((Test-Path -LiteralPath $configFile -PathType Leaf) -and -not $Force)) {
    $onboardArgs += "--verify-existing"
    Write-Host "Checking the saved pedalboard profile with fresh hardware discovery..."
} else {
    Write-Host "Starting unified read-only hardware onboarding..."
}
if ($PSBoundParameters.ContainsKey("Output")) { $onboardArgs += @("--output", $Output) }
if ($PSBoundParameters.ContainsKey("Model")) { $onboardArgs += @("--model", $Model) }
if ($PSBoundParameters.ContainsKey("Layout")) { $onboardArgs += @("--layout", $Layout) }
if ($PSBoundParameters.ContainsKey("MidiChannel")) { $onboardArgs += @("--midi-channel", $MidiChannel) }
if ($PSBoundParameters.ContainsKey("Firmware")) { $onboardArgs += @("--firmware", $Firmware) }
if ($PSBoundParameters.ContainsKey("Name")) { $onboardArgs += @("--name", $Name) }
if ($PSBoundParameters.ContainsKey("Address")) { $onboardArgs += @("--address", $Address) }
if ($PSBoundParameters.ContainsKey("ScanTimeout")) { $onboardArgs += @("--scan-timeout", $ScanTimeout) }
if ($NonInteractive) { $onboardArgs += "--non-interactive" }
if ($AcceptProfileStateDefaults) { $onboardArgs += "--accept-profile-state-defaults" }
if ($Force) { $onboardArgs += "--force" }
if ($Debug) { $onboardArgs += "--debug" }
if ($JsonLogs) { $onboardArgs += "--json-logs" }
if ($PSBoundParameters.ContainsKey("LogFile")) { $onboardArgs += @("--log-file", $LogFile) }

& $venvPythonExe -m blueboard_macro_handler @onboardArgs
exit $LASTEXITCODE
