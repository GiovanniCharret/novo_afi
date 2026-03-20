$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot

Write-Host "Instalando dependencias do frontend..."
Push-Location (Join-Path $root "frontend")
npm install

Write-Host "Gerando build estatico do frontend..."
npm run build
Pop-Location

Write-Host "Subindo a stack local do Novo AFI..."
docker compose -f (Join-Path $root "docker-compose.yml") up --build -d

Write-Host ""
Write-Host "Aplicacao disponivel em http://localhost:8000"
Write-Host "Healthcheck: http://localhost:8000/api/health"
