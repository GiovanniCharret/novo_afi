$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot

Write-Host "Subindo a stack local do Novo AFI..."
docker compose -f (Join-Path $root "docker-compose.yml") up --build -d

Write-Host ""
Write-Host "Aplicacao disponivel em http://localhost:8000"
Write-Host "Healthcheck: http://localhost:8000/api/health"
