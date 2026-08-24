$ErrorActionPreference = "Stop"
$pythonExe = Join-Path $PSScriptRoot "python\.venv\Scripts\python.exe"
$configFile = Join-Path $PSScriptRoot "python\config\katana-pedalboard.local.json"
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Python environment not found. Run .\setupPedalboard.ps1 first."
}
& $pythonExe -m blueboard_macro_handler configure --config $configFile @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Configuration complete. Test safely with: .\runPedalboard.ps1 --debug"
