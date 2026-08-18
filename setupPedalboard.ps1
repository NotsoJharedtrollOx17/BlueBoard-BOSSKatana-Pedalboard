param(
    [ValidateSet("venv", "global")][string]$Scope = "venv",
    [switch]$User,
    [switch]$Dev,
    [string]$PythonExe
)
$ErrorActionPreference = "Stop"
$repoRoot = $PSScriptRoot
$venvDir = Join-Path $repoRoot "python\.venv"
$venvPythonExe = Join-Path $venvDir "Scripts\python.exe"
$packageTarget = if ($Dev) { "$repoRoot[katana,dev]" } else { "$repoRoot[katana]" }

function Test-SupportedPython([string]$Candidate) {
    if (-not (Test-Path -LiteralPath $Candidate -PathType Leaf)) { return $false }
    try {
        $supported = & $Candidate -c "import sys; print(int((3, 10) <= sys.version_info[:2] < (3, 13)))"
        return $supported.Trim() -eq "1"
    } catch {
        return $false
    }
}

if ($PythonExe) {
    $PythonExe = (Resolve-Path -LiteralPath $PythonExe -ErrorAction Stop).Path
    if (-not (Test-SupportedPython $PythonExe)) {
        throw "-PythonExe must reference Python 3.10, 3.11, or 3.12."
    }
} else {
    $localPythonCandidates = @("Python312", "Python311", "Python310") |
        ForEach-Object { Join-Path $env:LOCALAPPDATA "Programs\Python\$_\python.exe" }
    $PythonExe = $localPythonCandidates | Where-Object { Test-SupportedPython $_ } | Select-Object -First 1
}

if (-not $PythonExe -and (Get-Command py -ErrorAction SilentlyContinue)) {
    foreach ($candidate in @("3.12", "3.11", "3.10")) {
        try {
            $candidateExe = (& py "-$candidate" -c "import sys; print(sys.executable)").Trim()
            if (Test-SupportedPython $candidateExe) {
                $PythonExe = $candidateExe
                break
            }
        } catch {
            continue
        }
    }
}
if (-not $PythonExe) {
    throw "Python 3.10, 3.11, or 3.12 is required because python-rtmidi 1.5.8 has no Windows wheel for Python 3.13+. Install a compatible runtime, or pass its path with -PythonExe."
}
Write-Host "Using Python: $PythonExe"

if ($Scope -eq "venv") {
    if (-not (Test-Path -LiteralPath $venvPythonExe)) {
        Write-Host "Creating python\.venv..."
        & $PythonExe -m venv $venvDir
    }
    $venvVersionIsSupported = & $venvPythonExe -c "import sys; print(int((3, 10) <= sys.version_info[:2] < (3, 13)))"
    if ($venvVersionIsSupported.Trim() -ne "1") {
        throw "python\.venv uses an unsupported Python version. Remove that generated environment, install Python 3.12, and rerun setup."
    }
    if ($Dev) {
        Write-Host "Updating the package build backend for development checks..."
        & $venvPythonExe -m pip install --upgrade "setuptools>=77" wheel
        if ($LASTEXITCODE -ne 0) { throw "Build-backend installation failed with exit code $LASTEXITCODE." }
    }
    Write-Host "Installing the BlueBoard/Katana bridge and MIDI backend..."
    & $venvPythonExe -m pip install --editable $packageTarget
    if ($LASTEXITCODE -ne 0) { throw "Package installation failed with exit code $LASTEXITCODE." }
    & $venvPythonExe -m blueboard_macro_handler --version
    Write-Host "Setup complete. Start with .\listKatanaMidiOutputs.ps1 and .\scanBlueBoard.ps1."
    exit 0
}

$installArgs = @("-m", "pip", "install", "--upgrade", $packageTarget)
if ($User) { $installArgs += "--user" }
& $PythonExe @installArgs
if ($LASTEXITCODE -ne 0) { throw "Global package installation failed with exit code $LASTEXITCODE." }

$scriptDirectories = @(
    (& $PythonExe -c "import sysconfig; print(sysconfig.get_path('scripts'))").Trim(),
    (& $PythonExe -c "import sysconfig; print(sysconfig.get_path('scripts', scheme='nt_user'))").Trim()
) | Select-Object -Unique
$executable = $scriptDirectories | ForEach-Object { Join-Path $_ "blueboard-katana.exe" } |
    Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $executable) {
    throw "Installation completed, but blueboard-katana.exe was not found in: $($scriptDirectories -join ', ')"
}
Write-Host "Global installation complete. Add the containing Scripts directory to PATH if needed:"
Write-Host (Split-Path -Parent $executable)
& $executable --version
