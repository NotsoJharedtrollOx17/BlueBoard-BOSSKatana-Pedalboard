param(
    [ValidateSet("main", "dev")][string]$Branch = "main",
    [ValidateSet("venv", "global")][string]$Scope = "venv",
    [switch]$User
)
$ErrorActionPreference = "Stop"
$repoRoot = $PSScriptRoot
$changes = @(git -C $repoRoot status --porcelain)
if ($LASTEXITCODE -ne 0) { throw "Could not inspect the Git repository." }
if ($changes.Count -gt 0) { throw "Update stopped: commit or stash local changes first." }

Write-Host "Updating $Branch from origin/$Branch..."
git -C $repoRoot fetch origin $Branch
if ($LASTEXITCODE -ne 0) { throw "Could not fetch origin/$Branch." }
git -C $repoRoot switch $Branch
if ($LASTEXITCODE -ne 0) { throw "Could not switch to $Branch." }
git -C $repoRoot pull --ff-only origin $Branch
if ($LASTEXITCODE -ne 0) { throw "Fast-forward update from origin/$Branch failed." }

$setupArgs = @("-Scope", $Scope)
if ($User) { $setupArgs += "-User" }
& (Join-Path $repoRoot "setupPedalboard.ps1") @setupArgs
