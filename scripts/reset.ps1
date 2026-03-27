$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $root "docker-compose.yml"
$pdfStorageDir = Join-Path $root "backend\banco_de_nf"

Write-Host "Derrubando a stack e removendo volumes do banco..."
docker compose -f $composeFile down -v

if (Test-Path -LiteralPath $pdfStorageDir) {
    Write-Host "Limpando PDFs salvos em $pdfStorageDir ..."
    Remove-Item -LiteralPath $pdfStorageDir -Recurse -Force
}

Write-Host "Ambiente resetado com sucesso."
