$ErrorActionPreference = "Stop"
$pythonExe = Join-Path $PSScriptRoot "python\.venv\Scripts\python.exe"
$configFile = Join-Path $PSScriptRoot "python\config\katana-pedalboard.local.json"
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Python environment not found. Run .\setupPedalboard.ps1 first."
}
if (-not (Test-Path -LiteralPath $configFile)) {
    throw "Local pedalboard configuration not found. Run .\configurePedalboard.ps1 first."
}
& $pythonExe -m blueboard_macro_handler doctor --config $configFile @args
exit $LASTEXITCODE
