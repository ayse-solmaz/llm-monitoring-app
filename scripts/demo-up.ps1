# Bring up the MLC demo stack (gateway + nginx + mlc×1 + observability).
# Does not start the Next.js frontend — prints the command when ready.
#
# Usage:
#   .\scripts\demo-up.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

function Test-DockerRunning {
    try {
        docker info 1>$null 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

Write-Host "Checking Docker Desktop ..."
if (-not (Test-DockerRunning)) {
    Write-Host "Docker is not running. Open Docker Desktop, wait until it is ready, then re-run."
    exit 1
}
Write-Host "Docker OK."

Write-Host "Starting compose (scale mlc=1) ..."
docker compose up -d --scale mlc=1
if ($LASTEXITCODE -ne 0) {
    Write-Host "docker compose up failed (exit $LASTEXITCODE)."
    exit $LASTEXITCODE
}

$healthUrl = "http://localhost:8080/healthz"
$modelsUrl = "http://localhost:8080/v1/models"
$maxAttempts = 90
$delaySec = 5

Write-Host "Waiting for gateway ready ($healthUrl) ..."
$ready = $false
for ($i = 1; $i -le $maxAttempts; $i++) {
    try {
        $resp = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 10
        $flag = $null
        if ($resp -is [bool]) {
            $flag = $resp
        } elseif ($null -ne $resp.ready) {
            $flag = [bool]$resp.ready
        } elseif ($null -ne $resp.status -and "$($resp.status)" -match "ok|ready|healthy") {
            $flag = $true
        } else {
            # Gateway up enough to answer /healthz — treat as ready if no ready field yet
            $flag = $true
        }
        if ($flag) {
            Write-Host "healthz ready (attempt $i)."
            $ready = $true
            break
        }
        Write-Host "  attempt ${i}/${maxAttempts} - not ready yet ..."
    } catch {
        Write-Host "  attempt ${i}/${maxAttempts} - $($_.Exception.Message)"
    }
    Start-Sleep -Seconds $delaySec
}

if (-not $ready) {
    Write-Host "Timed out waiting for $healthUrl ready."
    exit 1
}

Write-Host "Checking $modelsUrl ..."
try {
    $models = Invoke-RestMethod -Uri $modelsUrl -Method Get -TimeoutSec 30
    $ids = @()
    if ($models.data) {
        $ids = @($models.data | ForEach-Object { $_.id })
    }
    $joined = ($ids -join ", ")
    Write-Host "Models: $joined"
    if ($ids -notcontains "/app/model" -and ($joined -notmatch "/app/model")) {
        Write-Host "Warning: expected model id /app/model not clearly listed. Continue if Chat works."
    } else {
        Write-Host "Model /app/model OK."
    }
} catch {
    Write-Host "Failed to fetch /v1/models: $($_.Exception.Message)"
    exit 1
}

Write-Host @"

Stack is up.

Frontend (separate terminal):
  cd frontend
  npm run dev -- -p 3002

Chat: http://localhost:3002/chat
Gateway: http://localhost:8080/healthz

Tear down: .\scripts\demo-down.ps1
"@
