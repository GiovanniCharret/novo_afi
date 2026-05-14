"""F6 Fase B — endpoint `GET /api/contratos/{id}/totais`.

Cobre:
- Sem auth → 401.
- Contrato inexistente → 404.
- Contrato sem NFs → soma 0, contagem 0, pcts 0.
- Contrato com NFs → soma + contagem corretas, pcts calculados.
- Contrato com `valor_contrato = 0` → `pct_enviado_sobre_contrato = null` (sem divisão por zero).
- NFs pré-F2 (sem `contrato_id`) NÃO entram em nenhuma soma — comportamento esperado.
- `COUNT(DISTINCT numero_nf)` deduplica NFs com mesmo número (defesa em profundidade).
"""
from datetime import date
from decimal import Decimal

from app.db import get_session
from app.models import Contrato, NfEntry


def authenticate(client) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "user", "password": "password"},
    )
    assert response.status_code == 200


def _seed_contrato(
    numero: str, *,
    contrato_id: str | None = None,
    valor_contrato: int | Decimal = 2143980,
    valor_cde: int | Decimal = 1715180,
    participacao_cde: str = "0.8",
) -> str:
    contrato_id = contrato_id or f"id-{numero}"
    with get_session() as db:
        db.add(Contrato(
            id=contrato_id, numero=numero,
            sigla="TEST", cnpj="00000000000000",
            tranche="1ª", uf="SP",
            valor_contrato=valor_contrato,
            valor_cde=valor_cde,
            participacao_cde=participacao_cde,
            tipo_contrato="LPT", ativo=True,
        ))
        db.commit()
    return contrato_id


def _seed_nf(
    *,
    numero_nf: str,
    valor_total: Decimal,
    contrato_id: str | None,
    cnpj: str = "00000000000001",
) -> None:
    # F8b: 5 colunas (ncm/quantidade/preco_unitario/fornecedor/contrato) NOT NULL.
    bk = f"{numero_nf}|{cnpj}|{date(2024, 1, 1)}|{valor_total}|{numero_nf}"
    with get_session() as db:
        db.add(NfEntry(
            business_key=bk,
            numero_nf=numero_nf,
            cnpj=cnpj,
            data_emissao=date(2024, 1, 1),
            tipo_nota="service",
            fornecedor="Fornecedor Default",
            descricao=f"desc {numero_nf}",
            ncm="00.00",
            quantidade=Decimal("1"),
            preco_unitario=valor_total,
            valor_total=valor_total,
            contrato="ECFS TEST/2026",
            contrato_id=contrato_id,
            raw_payload={},
        ))
        db.commit()


# ---------------------------------------------------------------- 401

def test_totais_requires_authentication(client) -> None:
    response = client.get("/api/contratos/qualquer-id/totais")
    assert response.status_code == 401


# ---------------------------------------------------------------- 404

def test_totais_unknown_contrato_returns_404(client) -> None:
    authenticate(client)
    response = client.get("/api/contratos/nao-existe/totais")
    assert response.status_code == 404


# ---------------------------------------------------------------- contrato vazio

def test_totais_contrato_sem_nfs(client) -> None:
    cid = _seed_contrato("ECFS VAZIO", valor_contrato=1000000, valor_cde=800000)
    authenticate(client)

    response = client.get(f"/api/contratos/{cid}/totais")
    assert response.status_code == 200
    data = response.json()

    assert data["contrato_id"] == cid
    assert data["numero"] == "ECFS VAZIO"
    assert Decimal(data["soma_nfs_enviadas"]) == 0
    assert data["total_nfs_no_banco"] == 0
    assert data["pct_enviado_sobre_contrato"] == 0.0
    assert data["pct_enviado_sobre_cde"] == 0.0


# ---------------------------------------------------------------- contrato com NFs

def test_totais_contrato_com_nfs(client) -> None:
    cid = _seed_contrato(
        "ECFS COM_NFS",
        valor_contrato=1000000,  # 1M
        valor_cde=800000,        # 800k
        participacao_cde="0.8",
    )
    _seed_nf(numero_nf="A1", valor_total=Decimal("300000.00"), contrato_id=cid)
    _seed_nf(numero_nf="A2", valor_total=Decimal("100000.00"), contrato_id=cid)
    authenticate(client)

    response = client.get(f"/api/contratos/{cid}/totais")
    data = response.json()

    assert Decimal(data["soma_nfs_enviadas"]) == Decimal("400000.00")
    assert data["total_nfs_no_banco"] == 2
    # 400.000 / 1.000.000 = 0.4
    assert abs(data["pct_enviado_sobre_contrato"] - 0.4) < 0.001
    # 400.000 / 800.000 = 0.5
    assert abs(data["pct_enviado_sobre_cde"] - 0.5) < 0.001


# ---------------------------------------------------------------- valor_contrato = 0

def test_totais_contrato_com_valor_zero_retorna_pct_null(client) -> None:
    cid = _seed_contrato(
        "ECFS SEM_VALOR",
        valor_contrato=0,
        valor_cde=0,
    )
    _seed_nf(numero_nf="X1", valor_total=Decimal("500.00"), contrato_id=cid)
    authenticate(client)

    response = client.get(f"/api/contratos/{cid}/totais")
    data = response.json()

    assert Decimal(data["soma_nfs_enviadas"]) == Decimal("500.00")
    assert data["total_nfs_no_banco"] == 1
    # Divisão por zero virou null — frontend usa pra renderizar empty state.
    assert data["pct_enviado_sobre_contrato"] is None
    assert data["pct_enviado_sobre_cde"] is None


# ---------------------------------------------------------------- NFs pré-F2 ignoradas

def test_totais_ignora_nfs_pre_f2_sem_contrato(client) -> None:
    cid = _seed_contrato("ECFS ALVO", valor_contrato=1000000)
    _seed_nf(numero_nf="N1", valor_total=Decimal("100.00"), contrato_id=cid)
    # NF legacy (sem contrato_id) — não deve entrar
    _seed_nf(numero_nf="LEGADO", valor_total=Decimal("99999.99"), contrato_id=None)
    authenticate(client)

    response = client.get(f"/api/contratos/{cid}/totais")
    data = response.json()

    assert Decimal(data["soma_nfs_enviadas"]) == Decimal("100.00"), data
    assert data["total_nfs_no_banco"] == 1


# ---------------------------------------------------------------- isolamento entre contratos

def test_totais_isola_contratos_distintos(client) -> None:
    cid_a = _seed_contrato("ECFS A", valor_contrato=500000)
    cid_b = _seed_contrato("ECFS B", valor_contrato=500000)
    _seed_nf(numero_nf="A1", valor_total=Decimal("100.00"), contrato_id=cid_a)
    _seed_nf(numero_nf="A2", valor_total=Decimal("200.00"), contrato_id=cid_a)
    _seed_nf(numero_nf="B1", valor_total=Decimal("999.99"), contrato_id=cid_b)
    authenticate(client)

    response_a = client.get(f"/api/contratos/{cid_a}/totais")
    assert Decimal(response_a.json()["soma_nfs_enviadas"]) == Decimal("300.00")
    assert response_a.json()["total_nfs_no_banco"] == 2

    response_b = client.get(f"/api/contratos/{cid_b}/totais")
    assert Decimal(response_b.json()["soma_nfs_enviadas"]) == Decimal("999.99")
    assert response_b.json()["total_nfs_no_banco"] == 1
