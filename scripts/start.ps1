$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot

Write-Host "Carregando o frontend..."
Push-Location (Join-Path $root "frontend")
npm install

Write-Host "Rodando o frontend..."
npm run build
Pop-Location

Write-Host "Subindo o BD de NFs..."
docker compose -f (Join-Path $root "docker-compose.yml") up --build -d

