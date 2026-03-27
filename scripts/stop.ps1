$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot

Write-Host "Parando a stack local do Recebedor de NFs..."
docker compose -f (Join-Path $root "docker-compose.yml") down
