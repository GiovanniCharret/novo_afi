# Desenvolvimento Local

## Requisitos

- Docker
- Docker Compose

## Subir a stack

No PowerShell, a partir da raiz do projeto:

```powershell
.\scripts\start.ps1
```

## Parar a stack

```powershell
.\scripts\stop.ps1
```

## Endpoints iniciais

- Aplicacao: `http://localhost:8000/`
- Healthcheck: `http://localhost:8000/api/health`
- Exemplo de API: `http://localhost:8000/api/hello`

## O que esta pronto nesta fase

- Backend FastAPI com ponto de entrada em `backend/app/main.py`
- Pagina HTML estatica temporaria servida em `/`
- Chamada de frontend para a API em `/api/hello`
- PostgreSQL preparado no `docker-compose.yml` para as proximas etapas

## Observacao

O parser legado continua em `backend/app/main_v9.py` e ainda nao foi integrado ao backend web nesta fase.
