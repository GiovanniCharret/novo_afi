$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot

Write-Host "Parando a stack local do Novo AFI..."
docker compose -f (Join-Path $root "docker-compose.yml") down
