$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$compose = Join-Path $root "docker-compose.yml"

Write-Host "Carregando o frontend..."
Push-Location (Join-Path $root "frontend")
npm install

Write-Host "Rodando o frontend..."
npm run build
Pop-Location

Write-Host "Construindo a imagem do backend..."
docker compose -f $compose build

Write-Host "Subindo o banco de dados..."
docker compose -f $compose up -d db

Write-Host "Aplicando migrations Alembic (F2 — Decisão #3)..."
# `docker compose run --rm backend` espera a healthcheck do db (depends_on no compose).
# Schema é versionado: alembic upgrade head é idempotente; migrations já aplicadas
# viram no-op. Sair com falha aqui aborta o start (ErrorActionPreference = Stop).
docker compose -f $compose run --rm backend alembic upgrade head

Write-Host "Subindo o backend..."
docker compose -f $compose up -d backend

