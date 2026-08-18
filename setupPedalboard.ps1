param(
    [ValidateSet("venv", "global")][string]$Scope = "venv",
    [switch]$User,
    [switch]$Dev
)
$ErrorActionPreference = "Stop"
$repoRoot = $PSScriptRoot
$venvDir = Join-Path $repoRoot "python\.venv"
$pythonExe = Join-Path $venvDir "Scripts\python.exe"
$packageTarget = if ($Dev) { "$repoRoot[katana,dev]" } else { "$repoRoot[katana]" }

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python launcher 'py' was not found. Install Python 3.10, 3.11, or 3.12 and retry."
}

$pythonVersionArg = $null
try {
    $availableRuntimes = @(py -0p)
} catch {
    throw "Could not query installed Python runtimes with 'py -0p'."
}
foreach ($candidate in @("3.12", "3.11", "3.10")) {
    if ($availableRuntimes | Where-Object { $_ -match "-V:$([regex]::Escape($candidate))\s" }) {
        $pythonVersionArg = "-$candidate"
        break
    }
}
if (-not $pythonVersionArg) {
    throw "Python 3.10, 3.11, or 3.12 is required because python-rtmidi 1.5.8 has no Windows wheel for Python 3.13+. Install Python 3.12 and retry."
}

if ($Scope -eq "venv") {
    if (-not (Test-Path -LiteralPath $pythonExe)) {
        Write-Host "Creating python\.venv..."
        & py $pythonVersionArg -m venv $venvDir
    }
    $venvVersionIsSupported = & $pythonExe -c "import sys; print(int((3, 10) <= sys.version_info[:2] < (3, 13)))"
    if ($venvVersionIsSupported.Trim() -ne "1") {
        throw "python\.venv uses an unsupported Python version. Remove that generated environment, install Python 3.12, and rerun setup."
    }
    Write-Host "Installing the BlueBoard/Katana bridge and MIDI backend..."
    & $pythonExe -m pip install --editable $packageTarget
    if ($LASTEXITCODE -ne 0) { throw "Package installation failed with exit code $LASTEXITCODE." }
    & $pythonExe -m blueboard_macro_handler --version
    Write-Host "Setup complete. Start with .\listKatanaMidiOutputs.ps1 and .\scanBlueBoard.ps1."
    exit 0
}

$installArgs = @("-m", "pip", "install", "--upgrade", $packageTarget)
if ($User) { $installArgs += "--user" }
& py $pythonVersionArg @installArgs
if ($LASTEXITCODE -ne 0) { throw "Global package installation failed with exit code $LASTEXITCODE." }

$scriptDirectories = @(
    (& py $pythonVersionArg -c "import sysconfig; print(sysconfig.get_path('scripts'))").Trim(),
    (& py $pythonVersionArg -c "import sysconfig; print(sysconfig.get_path('scripts', scheme='nt_user'))").Trim()
) | Select-Object -Unique
$executable = $scriptDirectories | ForEach-Object { Join-Path $_ "blueboard-katana.exe" } |
    Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $executable) {
    throw "Installation completed, but blueboard-katana.exe was not found in: $($scriptDirectories -join ', ')"
}
Write-Host "Global installation complete. Add the containing Scripts directory to PATH if needed:"
Write-Host (Split-Path -Parent $executable)
& $executable --version
