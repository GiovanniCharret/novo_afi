"""F2 — seed da tabela `contratos` a partir de `base_contratos.json`.

Idempotente: roda no `lifespan` após `init_db()`. Re-rodar com mesmo JSON
não duplica porque ID é UUID5 determinístico derivado de `numero`. Se o
JSON mudar, valores são atualizados (UPSERT semântico via get-then-update).

Path do JSON: mesmo que `contrato_config.py` usa (Decisão #4 + bind mount
no `docker-compose.yml`). Fonte de verdade documentada em CLAUDE.md é a
raiz do projeto; bind mount expõe lá em `backend/app/base_contratos.json`.
"""
import json
import uuid
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Contrato


# Mesmo path que `contrato_config.py:16` usa. Em Docker, é o bind mount
# do `docker-compose.yml` apontando para a raiz do projeto.
BASE_CONTRATOS_PATH = Path(__file__).resolve().parent.parent / "base_contratos.json"

# Namespace UUID arbitrário mas FIXO para gerar UUID5 determinístico dos
# contratos. NÃO mudar — IDs já existentes em DB ficariam órfãos.
# Não usei NAMESPACE_DNS porque "ECFS 101/2005" não é nome de domínio.
_CONTRATO_NAMESPACE = uuid.UUID("8d4b6c0e-1f2a-4b3c-9d5e-7f6a8b9c0d1e")

CAMPOS_OBRIGATORIOS = ("sigla", "cnpj", "tipo_contrato")
CAMPOS_NUMERICOS = ("valor_contrato", "valor_cde", "participacao_cde")


def _uuid_for_numero(numero: str) -> str:
    """UUID5 determinístico para um número de contrato."""
    return str(uuid.uuid5(_CONTRATO_NAMESPACE, numero))


def _validate_entry(numero: str, info: dict) -> None:
    """Checagem pragmática de shape (adversarial review #31). Falha cedo
    com erro claro; rigor maior (pydantic) é overkill para JSON estático
    de ~140 entradas.
    """
    if not isinstance(info, dict):
        raise ValueError(
            f"contrato {numero!r}: esperado dict, recebido {type(info).__name__}"
        )
    for campo in CAMPOS_OBRIGATORIOS:
        valor = info.get(campo)
        if valor is None or (isinstance(valor, str) and not valor.strip()):
            raise ValueError(
                f"contrato {numero!r}: campo obrigatório {campo!r} faltando ou vazio"
            )
    for campo in CAMPOS_NUMERICOS:
        valor = info.get(campo, 0)
        if not isinstance(valor, (int, float)):
            raise ValueError(
                f"contrato {numero!r}: campo {campo!r} deve ser numérico, "
                f"recebido {type(valor).__name__}"
            )


def _load_base_contratos_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"base_contratos.json não encontrado em {path}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(
            f"{path}: esperado JSON object (top-level dict), "
            f"recebido {type(data).__name__}"
        )
    return data


def seed_contratos(db: Session, *, json_path: Path | None = None) -> int:
    """Roda UPSERT de cada entrada de base_contratos.json em `contratos`.

    Retorna total de contratos seedados (criados + atualizados). Idempotente:
    re-rodar com mesmo JSON é no-op semântico. Falha cedo se shape inválido.
    """
    base = _load_base_contratos_json(json_path or BASE_CONTRATOS_PATH)
    total = 0
    for numero, info in base.items():
        _validate_entry(numero, info)
        contrato_id = _uuid_for_numero(numero)
        existente = db.get(Contrato, contrato_id)
        if existente is None:
            db.add(Contrato(
                id=contrato_id,
                numero=numero,
                sigla=info["sigla"],
                cnpj=info["cnpj"],
                tranche=info.get("tranche"),
                uf=info.get("uf"),
                valor_contrato=Decimal(str(info.get("valor_contrato", 0))),
                valor_cde=Decimal(str(info.get("valor_cde", 0))),
                participacao_cde=Decimal(str(info.get("participacao_cde", 0))),
                tipo_contrato=info["tipo_contrato"],
                ativo=True,
            ))
        else:
            # UPDATE — valores podem ter mudado no JSON (adversarial #32 alerta:
            # mudança acidental sobrescreve. Aceito nesta fase, sem versionamento).
            existente.sigla = info["sigla"]
            existente.cnpj = info["cnpj"]
            existente.tranche = info.get("tranche")
            existente.uf = info.get("uf")
            existente.valor_contrato = Decimal(str(info.get("valor_contrato", 0)))
            existente.valor_cde = Decimal(str(info.get("valor_cde", 0)))
            existente.participacao_cde = Decimal(str(info.get("participacao_cde", 0)))
            existente.tipo_contrato = info["tipo_contrato"]
        total += 1
    db.commit()
    return total
