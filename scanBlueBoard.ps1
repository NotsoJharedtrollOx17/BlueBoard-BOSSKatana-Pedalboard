$ErrorActionPreference = "Stop"
$pythonExe = Join-Path $PSScriptRoot "python\.venv\Scripts\python.exe"
$configFile = Join-Path $PSScriptRoot "python\config\blueboard.json"
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Python environment not found. Run .\setupPedalboard.ps1 first."
}
& $pythonExe -m blueboard_macro_handler scan --config $configFile --scan-timeout 20 @args
