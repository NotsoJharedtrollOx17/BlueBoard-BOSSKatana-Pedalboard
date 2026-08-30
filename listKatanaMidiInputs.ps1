$ErrorActionPreference = "Stop"
$pythonExe = Join-Path $PSScriptRoot "python\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Python environment not found. Run .\setupPedalboard.ps1 first."
}
& $pythonExe -m blueboard_macro_handler midi-inputs @args
exit $LASTEXITCODE
