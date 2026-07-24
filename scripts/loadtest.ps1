# Load test for MLC scaling stack via nginx (:8080).
#
# Default: 50 total requests, 3 concurrent workers (match typical replica count).
# Use -Concurrent equal to your mlc replica count to avoid nginx 502s.
#
# Why not 200/20 (assignment baseline)?
# CPU inference on Gemma 2B q4f16_1 takes ~25 s per request on this host
# (16 logical cores, 4 CPU limit per replica). At 200 requests x ~25 s with
# low concurrency, a single run would exceed 60 minutes; at 20 concurrent,
# replicas would queue heavily and distort latency. 50/3 gives a manageable run
# that still shows scaling behaviour without exhausting the machine.
#
# Usage:
#   .\scripts\loadtest.ps1
#   .\scripts\loadtest.ps1 -Total 30 -Concurrent 4 -BaseUrl http://localhost:8080

param(
    [int]$Total = 50,
    [int]$Concurrent = 3,
    [string]$BaseUrl = "http://localhost:8080",
    [int]$MaxTokens = 32
)

$ErrorActionPreference = "Stop"

$endpoint = "$BaseUrl/v1/chat/completions"

function Invoke-ChatRequest {
    param([int]$Id, [string]$Uri, [int]$Tokens)
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $body = @{
        model      = "gemma-2b-it"
        messages   = @(@{ role = "user"; content = "Reply with one short sentence for request $Id." })
        stream     = $false
        max_tokens = $Tokens
    } | ConvertTo-Json -Compress
    try {
        $null = Invoke-RestMethod -Uri $Uri -Method Post -ContentType "application/json" -Body $body -TimeoutSec 600
        $sw.Stop()
        return [PSCustomObject]@{ Id = $Id; Ms = $sw.ElapsedMilliseconds; Ok = $true }
    }
    catch {
        $sw.Stop()
        return [PSCustomObject]@{ Id = $Id; Ms = $sw.ElapsedMilliseconds; Ok = $false; Error = $_.Exception.Message }
    }
}

Write-Host "Load test: $Total requests, $Concurrent concurrent -> $endpoint"
Write-Host ""

$results = New-Object System.Collections.Generic.List[object]
$pending = New-Object System.Collections.Generic.Queue[int]
1..$Total | ForEach-Object { $pending.Enqueue($_) }

$overall = [System.Diagnostics.Stopwatch]::StartNew()

while ($pending.Count -gt 0) {
    $batch = @()
    while ($batch.Count -lt $Concurrent -and $pending.Count -gt 0) {
        $batch += $pending.Dequeue()
    }

    $jobs = foreach ($id in $batch) {
        Start-Job -ScriptBlock {
            param($Id, $Uri, $Tokens)
            $sw = [System.Diagnostics.Stopwatch]::StartNew()
            $body = @{
                model      = "gemma-2b-it"
                messages   = @(@{ role = "user"; content = "Reply with one short sentence for request $Id." })
                stream     = $false
                max_tokens = $Tokens
            } | ConvertTo-Json -Compress
            try {
                $null = Invoke-RestMethod -Uri $Uri -Method Post -ContentType "application/json" -Body $body -TimeoutSec 600
                $sw.Stop()
                [PSCustomObject]@{ Id = $Id; Ms = $sw.ElapsedMilliseconds; Ok = $true }
            }
            catch {
                $sw.Stop()
                [PSCustomObject]@{ Id = $Id; Ms = $sw.ElapsedMilliseconds; Ok = $false; Error = $_.Exception.Message }
            }
        } -ArgumentList $id, $endpoint, $MaxTokens
    }

    $jobs | Wait-Job | Receive-Job -ErrorAction SilentlyContinue | ForEach-Object { [void]$results.Add($_) }
    $jobs | Remove-Job -Force
}

$overall.Stop()

$latencies = @($results | Where-Object { $_.Ok } | Select-Object -ExpandProperty Ms | Sort-Object)
$failedResults = @($results | Where-Object { -not $_.Ok })
$failed = $failedResults.Count
$ok = $latencies.Count

if ($ok -eq 0) {
    Write-Error "All $Total requests failed."
    $failedResults | Select-Object -First 5 | ForEach-Object {
        Write-Host "  request $($_.Id): $($_.Error)"
    }
    exit 1
}

function Get-Percentile([double[]]$sorted, [double]$p) {
    if ($sorted.Length -eq 0) { return 0 }
    $idx = [math]::Ceiling($p / 100.0 * $sorted.Length) - 1
    if ($idx -lt 0) { $idx = 0 }
    if ($idx -ge $sorted.Length) { $idx = $sorted.Length - 1 }
    return [int]$sorted[$idx]
}

$avg = [math]::Round(($latencies | Measure-Object -Average).Average, 0)
$p50 = Get-Percentile $latencies 50
$p95 = Get-Percentile $latencies 95
$rps = [math]::Round($ok / $overall.Elapsed.TotalSeconds, 3)

Write-Host "=== Results ==="
Write-Host "Total wall time : $([math]::Round($overall.Elapsed.TotalSeconds, 1)) s"
Write-Host "Successful      : $ok / $Total ($failed failed)"
Write-Host "Throughput      : $rps req/s"
Write-Host "Latency avg     : ${avg} ms"
Write-Host "Latency p50     : ${p50} ms"
Write-Host "Latency p95     : ${p95} ms"
