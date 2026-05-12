"""F3b Fase B — filtros opcionais em `GET /api/nf-entries`.

Cobre:
- Regressão: sem params, response idêntica ao comportamento atual.
- contrato_id isolado.
- q (busca livre) em cada uma das 4 colunas alvo + case-insensitive.
- data_inicio / data_fim inclusivos (intervalo fechado).
- valor_min / valor_max inclusivos (intervalo fechado).
- tipo_nota igualdade exata.
- Combinação AND de múltiplos filtros.
- Base vazia (zero matches) retorna lista vazia, não 404.

Setup: cada teste seedaA contratos + NFs direto no DB (sem subir parser).
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


def _seed_contrato(numero: str, contrato_id: str | None = None) -> str:
    contrato_id = contrato_id or f"id-{numero}"
    with get_session() as db:
        db.add(Contrato(
            id=contrato_id, numero=numero,
            sigla="TEST", cnpj="00000000000000",
            tranche="1ª", uf="SP",
            valor_contrato=0, valor_cde=0, participacao_cde="0",
            tipo_contrato="LPT", ativo=True,
        ))
        db.commit()
    return contrato_id


def _seed_nf(
    *,
    numero_nf: str = "1",
    cnpj: str = "00000000000001",
    data_emissao: date = date(2024, 6, 15),
    tipo_nota: str = "service",
    fornecedor: str = "Fornecedor Default",
    descricao: str = "Serviço padrão",
    valor_total: Decimal = Decimal("100.00"),
    contrato_id: str | None = None,
) -> str:
    """Cria uma NfEntry mínima. business_key derivada dos campos para
    permitir múltiplas NFs no mesmo teste sem colisão UNIQUE."""
    bk = f"{numero_nf}|{cnpj}|{data_emissao}|{valor_total}|{descricao}"
    with get_session() as db:
        nf = NfEntry(
            business_key=bk,
            numero_nf=numero_nf,
            cnpj=cnpj,
            data_emissao=data_emissao,
            tipo_nota=tipo_nota,
            fornecedor=fornecedor,
            descricao=descricao,
            valor_total=valor_total,
            contrato_id=contrato_id,
            raw_payload={},
        )
        db.add(nf)
        db.commit()
        return nf.id


# -------- Regressão: sem params --------

def test_no_filters_returns_all_entries(client) -> None:
    """Sem query params, response inclui todas as NFs do banco — preserva o
    comportamento usado pela tabela principal de upload (F2 e anteriores)."""
    authenticate(client)
    _seed_nf(numero_nf="A", descricao="primeira")
    _seed_nf(numero_nf="B", descricao="segunda")
    _seed_nf(numero_nf="C", descricao="terceira")

    response = client.get("/api/nf-entries")
    assert response.status_code == 200
    assert len(response.json()) == 3


# -------- contrato_id --------

def test_filter_by_contrato_id(client) -> None:
    authenticate(client)
    cid_a = _seed_contrato("ECFS A")
    cid_b = _seed_contrato("ECFS B")
    _seed_nf(numero_nf="1", descricao="da A", contrato_id=cid_a)
    _seed_nf(numero_nf="2", descricao="da A tambem", contrato_id=cid_a)
    _seed_nf(numero_nf="3", descricao="da B", contrato_id=cid_b)
    _seed_nf(numero_nf="4", descricao="sem contrato")  # contrato_id=None

    response = client.get(f"/api/nf-entries?contrato_id={cid_a}")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert {e["numero_nf"] for e in data} == {"1", "2"}


# -------- q (busca livre em 4 colunas via OR, case-insensitive) --------

def test_q_matches_numero_nf(client) -> None:
    authenticate(client)
    _seed_nf(numero_nf="NF-2024-001", descricao="x")
    _seed_nf(numero_nf="NF-2024-002", descricao="y")
    _seed_nf(numero_nf="OUTRO-99", descricao="z")

    response = client.get("/api/nf-entries?q=2024")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


def test_q_matches_fornecedor(client) -> None:
    authenticate(client)
    _seed_nf(numero_nf="1", fornecedor="EMPRESA ALPHA")
    _seed_nf(numero_nf="2", fornecedor="empresa beta")
    _seed_nf(numero_nf="3", fornecedor="OUTRO")

    response = client.get("/api/nf-entries?q=empresa")
    data = response.json()
    assert len(data) == 2, f"esperado 2 (case-insensitive), recebido {len(data)}"


def test_q_matches_cnpj(client) -> None:
    authenticate(client)
    _seed_nf(numero_nf="1", cnpj="12345678000100")
    _seed_nf(numero_nf="2", cnpj="98765432000100")

    response = client.get("/api/nf-entries?q=1234567")
    data = response.json()
    assert len(data) == 1
    assert data[0]["numero_nf"] == "1"


def test_q_matches_descricao(client) -> None:
    authenticate(client)
    _seed_nf(numero_nf="1", descricao="Serviço de instalação elétrica")
    _seed_nf(numero_nf="2", descricao="Mão de obra de pintura")

    response = client.get("/api/nf-entries?q=instala")
    data = response.json()
    assert len(data) == 1
    assert data[0]["numero_nf"] == "1"


# -------- data_inicio / data_fim --------

def test_date_range_inclusive(client) -> None:
    authenticate(client)
    _seed_nf(numero_nf="1", data_emissao=date(2024, 5, 31))
    _seed_nf(numero_nf="2", data_emissao=date(2024, 6, 1))
    _seed_nf(numero_nf="3", data_emissao=date(2024, 6, 30))
    _seed_nf(numero_nf="4", data_emissao=date(2024, 7, 1))

    response = client.get("/api/nf-entries?data_inicio=2024-06-01&data_fim=2024-06-30")
    data = response.json()
    assert len(data) == 2
    assert {e["numero_nf"] for e in data} == {"2", "3"}


def test_data_inicio_only(client) -> None:
    authenticate(client)
    _seed_nf(numero_nf="1", data_emissao=date(2024, 1, 1))
    _seed_nf(numero_nf="2", data_emissao=date(2024, 12, 31))

    response = client.get("/api/nf-entries?data_inicio=2024-06-01")
    data = response.json()
    assert len(data) == 1
    assert data[0]["numero_nf"] == "2"


# -------- valor_min / valor_max --------

def test_valor_range_inclusive(client) -> None:
    authenticate(client)
    _seed_nf(numero_nf="1", valor_total=Decimal("999.99"), descricao="abaixo")
    _seed_nf(numero_nf="2", valor_total=Decimal("1000.00"), descricao="limite inf")
    _seed_nf(numero_nf="3", valor_total=Decimal("3500.50"), descricao="meio")
    _seed_nf(numero_nf="4", valor_total=Decimal("5000.00"), descricao="limite sup")
    _seed_nf(numero_nf="5", valor_total=Decimal("5000.01"), descricao="acima")

    response = client.get("/api/nf-entries?valor_min=1000&valor_max=5000")
    data = response.json()
    assert len(data) == 3
    assert {e["numero_nf"] for e in data} == {"2", "3", "4"}


# -------- tipo_nota --------

def test_filter_by_tipo_nota_exact(client) -> None:
    authenticate(client)
    _seed_nf(numero_nf="1", tipo_nota="service", descricao="a")
    _seed_nf(numero_nf="2", tipo_nota="service", descricao="b")
    _seed_nf(numero_nf="3", tipo_nota="produto", descricao="c")

    response = client.get("/api/nf-entries?tipo_nota=service")
    data = response.json()
    assert len(data) == 2


# -------- Combinação AND --------

def test_combination_of_filters_is_and(client) -> None:
    """contrato_id + q + intervalo de data + valor combinam por AND."""
    authenticate(client)
    cid = _seed_contrato("ECFS X")
    # Match completo (todos os filtros): único alvo
    _seed_nf(
        numero_nf="100", contrato_id=cid,
        descricao="instalação elétrica",
        data_emissao=date(2024, 6, 15),
        valor_total=Decimal("2500.00"),
    )
    # Falha por contrato
    _seed_nf(numero_nf="101", descricao="instalação", data_emissao=date(2024, 6, 15), valor_total=Decimal("2500.00"))
    # Falha por q
    _seed_nf(numero_nf="102", contrato_id=cid, descricao="manutenção", data_emissao=date(2024, 6, 15), valor_total=Decimal("2500.00"))
    # Falha por data
    _seed_nf(numero_nf="103", contrato_id=cid, descricao="instalação", data_emissao=date(2023, 1, 1), valor_total=Decimal("2500.00"))
    # Falha por valor
    _seed_nf(numero_nf="104", contrato_id=cid, descricao="instalação", data_emissao=date(2024, 6, 15), valor_total=Decimal("50.00"))

    response = client.get(
        f"/api/nf-entries?contrato_id={cid}"
        "&q=instala&data_inicio=2024-01-01&data_fim=2024-12-31"
        "&valor_min=1000&valor_max=5000"
    )
    data = response.json()
    assert len(data) == 1, f"esperado 1 (AND estrito), recebido {len(data)}"
    assert data[0]["numero_nf"] == "100"


# -------- Base vazia --------

def test_filters_with_no_matches_return_empty_list(client) -> None:
    authenticate(client)
    _seed_nf(numero_nf="1", descricao="abc")

    response = client.get("/api/nf-entries?q=zzz_nada_bate")
    assert response.status_code == 200
    assert response.json() == []
