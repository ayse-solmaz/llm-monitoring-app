# Stop the MLC demo compose stack. Does not delete volumes.
#
# Usage:
#   .\scripts\demo-down.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "Stopping compose (volumes kept) ..."
docker compose down
if ($LASTEXITCODE -ne 0) {
    Write-Host "docker compose down failed (exit $LASTEXITCODE)."
    exit $LASTEXITCODE
}
Write-Host "Done."
