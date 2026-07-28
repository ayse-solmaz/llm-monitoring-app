# After Ollama is installed — pull Arc model and point the stack at it.
# ARCHIVED — Ollama rejected; see archive/ADR-001-ollama-rejected.md
# Docs: archive/docs/ARC_OLLAMA.md

$ErrorActionPreference = "Stop"
$ollama = @(
  "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe",
  "C:\Program Files\Ollama\ollama.exe",
  "ollama"
) | Where-Object { $_ -eq "ollama" -or (Test-Path $_) } | Select-Object -First 1

if (-not $ollama) {
  Write-Host "Ollama not found. Install from https://ollama.com/download/windows then re-run."
  exit 1
}

$model = if ($args[0]) { $args[0] } else { "qwen2.5:1.5b" }
Write-Host "Using: $ollama"
Write-Host "Pulling $model ..."
& $ollama pull $model

Write-Host "Smoke: ollama run $model Hi"
& $ollama run $model "Hi"

Set-Location $PSScriptRoot\..\..
Write-Host "Restarting gateway → host Ollama ..."
docker compose -f docker-compose.yml -f archive/docker-compose.ollama.yml up -d gateway
docker compose stop mlc 2>$null

Write-Host @"

Next:
  1. Edit frontend\.env.local:
       MLC_UPSTREAM=http://127.0.0.1:11434
       NEXT_PUBLIC_MLC_MODEL_ID=$model
  2. cd frontend; npm run dev -- -p 3002
  3. Open http://localhost:3002/chat
"@
