# Resilient overnight HF download for q0f16 weights.
# Retries forever until shard/meta completeness checks pass.
# Does NOT touch prod. Safe to leave running overnight on bad networks.

$ErrorActionPreference = "Continue"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$LocalDir = Join-Path $RepoRoot "backups\q0f16-weights"
$RepoId = "ayse-solmaz/gemma-2b-it-tr-q0f16"
$MinShards = 49
$MinBytes = [int64](4.5 * 1GB)
$SleepSeconds = 30
$Attempt = 0

$RequiredFiles = @(
    "tensor-cache.json",
    "gemma-cpu.so",
    "mlc-chat-config.json",
    "tokenizer.json"
)

function Get-DownloadProgress {
    param([string]$Dir)

    if (-not (Test-Path $Dir)) {
        return [pscustomobject]@{
            Shards   = 0
            Bytes    = [int64]0
            GB       = 0.0
            Missing  = @($RequiredFiles)
            Complete = $false
        }
    }

    $files = Get-ChildItem -Path $Dir -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch '[\\/]\.cache[\\/]' }

    $shards = @($files | Where-Object { $_.Name -like 'params_shard_*.bin' }).Count
    $bytes = [int64](($files | Measure-Object -Property Length -Sum).Sum)
    if (-not $bytes) { $bytes = [int64]0 }

    $missing = @()
    foreach ($name in $RequiredFiles) {
        if (-not (Test-Path (Join-Path $Dir $name))) {
            $missing += $name
        }
    }

    $complete = ($shards -ge $MinShards) -and ($missing.Count -eq 0) -and ($bytes -ge $MinBytes)

    return [pscustomobject]@{
        Shards   = $shards
        Bytes    = $bytes
        GB       = [math]::Round($bytes / 1GB, 2)
        Missing  = $missing
        Complete = $complete
    }
}

function Write-ProgressLine {
    param($Progress, [int]$AttemptNum, [string]$Phase)

    $missingText = if ($Progress.Missing.Count -gt 0) {
        ($Progress.Missing -join ", ")
    } else {
        "none"
    }

    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host ("[{0}] {1} attempt={2} shards={3}/{4} size={5} GB missing=[{6}]" -f `
        $ts, $Phase, $AttemptNum, $Progress.Shards, $MinShards, $Progress.GB, $missingText)
}

New-Item -ItemType Directory -Force -Path $LocalDir | Out-Null

Write-Host "=== q0f16 overnight resume download ==="
Write-Host "HF repo : $RepoId"
Write-Host "Local   : $LocalDir"
Write-Host "Done when: >=$MinShards shards, required meta files, total >=4.5 GB"
Write-Host "Retries forever; sleep ${SleepSeconds}s on failure. Ctrl+C to stop."
Write-Host ""

$initial = Get-DownloadProgress -Dir $LocalDir
Write-ProgressLine -Progress $initial -AttemptNum 0 -Phase "START"

if ($initial.Complete) {
    Write-Host "Already complete. Nothing to download."
    exit 0
}

# Prefer long timeouts so flaky links do not abort early mid-shard.
$env:HF_HUB_DOWNLOAD_TIMEOUT = "600"
$env:HF_HUB_ETAG_TIMEOUT = "60"

while ($true) {
    $Attempt++
    $before = Get-DownloadProgress -Dir $LocalDir
    Write-ProgressLine -Progress $before -AttemptNum $Attempt -Phase "BEFORE"

    Write-Host ("[{0}] Running: hf download {1} --local-dir {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $RepoId, $LocalDir)

    & hf download $RepoId --local-dir $LocalDir
    $exitCode = $LASTEXITCODE

    $after = Get-DownloadProgress -Dir $LocalDir
    Write-ProgressLine -Progress $after -AttemptNum $Attempt -Phase "AFTER"

    if ($after.Complete) {
        Write-Host ""
        Write-Host "SUCCESS: q0f16 local seed ready."
        Write-Host ("  shards={0} size={1} GB" -f $after.Shards, $after.GB)
        Write-Host "  Prod untouched. Next step is diag seed only when you are ready."
        exit 0
    }

    if ($exitCode -eq 0) {
        Write-Host "hf exited 0 but completeness check failed - will retry."
    } else {
        Write-Host ("hf failed (exit {0}) - will retry after {1}s." -f $exitCode, $SleepSeconds)
    }

    Start-Sleep -Seconds $SleepSeconds
}
