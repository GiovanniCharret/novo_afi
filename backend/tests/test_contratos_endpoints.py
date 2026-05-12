"""F2 B3 — testes dos endpoints de contratos e da dependency `require_contrato`.

A fixture `client` faz init_db() (sem seed automático, porque o JSON real
não está presente em testes locais — lifespan captura FileNotFoundError).
Cada teste popula `Contrato` manualmente via session direta.
"""
from app.db import get_session
from app.dependencies import require_contrato
from app.models import Contrato

import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock


def authenticate(client) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "user", "password": "password"},
    )
    assert response.status_code == 200


def _seed_contratos(rows: list[dict]) -> None:
    """Insere contratos diretamente no DB do teste (sem usar o seed do JSON).

    Cada `row` é um dict com {id, numero, sigla, ..., ativo}.
    """
    with get_session() as db:
        for row in rows:
            db.add(Contrato(**row))
        db.commit()


def _sample_contrato(numero: str, *, ativo: bool = True, **overrides) -> dict:
    base = {
        "id": f"id-{numero}",
        "numero": numero,
        "sigla": "CPFL",
        "cnpj": "53859112000169",
        "tranche": "2ª Tranche",
        "uf": "SP",
        "valor_contrato": 2143980,
        "valor_cde": 1715180,
        "participacao_cde": "0.8",
        "tipo_contrato": "LPT",
        "ativo": ativo,
    }
    base.update(overrides)
    return base


# -------- GET /api/contratos --------

def test_list_contratos_requires_authentication(client) -> None:
    response = client.get("/api/contratos")
    assert response.status_code == 401


def test_list_contratos_returns_only_ativos_ordered(client) -> None:
    _seed_contratos([
        _sample_contrato("ECFS 200/2010"),
        _sample_contrato("ECFS 100/2005"),
        _sample_contrato("ECFS 999/9999", ativo=False),
    ])
    authenticate(client)

    response = client.get("/api/contratos")

    assert response.status_code == 200
    rows = response.json()
    numeros = [r["numero"] for r in rows]
    assert numeros == ["ECFS 100/2005", "ECFS 200/2010"]  # ordenado, sem inativo


# -------- POST /api/session/contrato --------

def test_set_session_contrato_requires_authentication(client) -> None:
    response = client.post("/api/session/contrato", json={"contrato_id": "qualquer"})
    assert response.status_code == 401


def test_set_session_contrato_with_valid_id_persists(client) -> None:
    _seed_contratos([_sample_contrato("ECFS 100/2005")])
    authenticate(client)

    response = client.post(
        "/api/session/contrato",
        json={"contrato_id": "id-ECFS 100/2005"},
    )

    assert response.status_code == 200
    assert response.json()["numero"] == "ECFS 100/2005"

    # Confirma que persiste — GET subsequente retorna o mesmo contrato.
    get_resp = client.get("/api/session/contrato")
    assert get_resp.status_code == 200
    assert get_resp.json()["numero"] == "ECFS 100/2005"


def test_set_session_contrato_inactive_returns_404(client) -> None:
    _seed_contratos([_sample_contrato("ECFS 999/9999", ativo=False)])
    authenticate(client)

    response = client.post(
        "/api/session/contrato",
        json={"contrato_id": "id-ECFS 999/9999"},
    )

    # 404 (não 403) — não vazar existência (adversarial #21).
    assert response.status_code == 404


def test_set_session_contrato_inexistent_returns_404(client) -> None:
    authenticate(client)

    response = client.post(
        "/api/session/contrato",
        json={"contrato_id": "id-que-nao-existe"},
    )

    assert response.status_code == 404


def test_set_session_contrato_double_click_is_idempotent(client) -> None:
    """Adversarial #30 — double-click não corrompe estado."""
    _seed_contratos([_sample_contrato("ECFS 100/2005")])
    authenticate(client)

    r1 = client.post("/api/session/contrato", json={"contrato_id": "id-ECFS 100/2005"})
    r2 = client.post("/api/session/contrato", json={"contrato_id": "id-ECFS 100/2005"})

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json() == r2.json()


# -------- GET /api/session/contrato --------

def test_get_session_contrato_requires_authentication(client) -> None:
    response = client.get("/api/session/contrato")
    assert response.status_code == 401


def test_get_session_contrato_without_selection_returns_404(client) -> None:
    authenticate(client)

    response = client.get("/api/session/contrato")

    assert response.status_code == 404


def test_get_session_contrato_after_contrato_deactivated_clears_session(client) -> None:
    """Se contrato foi desativado entre seleção e consulta, GET retorna 404
    e limpa a sessão (defesa contra estado stale).
    """
    _seed_contratos([_sample_contrato("ECFS 100/2005")])
    authenticate(client)
    client.post("/api/session/contrato", json={"contrato_id": "id-ECFS 100/2005"})

    # Simula desativação direto no DB
    with get_session() as db:
        c = db.get(Contrato, "id-ECFS 100/2005")
        c.ativo = False
        db.commit()

    response = client.get("/api/session/contrato")
    assert response.status_code == 404


# -------- require_contrato dependency --------

def test_require_contrato_raises_401_without_auth():
    """B4 — auth precede contrato. Sessão vazia → 401, não 400."""
    fake_request = MagicMock()
    fake_request.session = {}

    with pytest.raises(HTTPException) as exc_info:
        require_contrato(fake_request)
    assert exc_info.value.status_code == 401


def test_require_contrato_raises_400_authenticated_without_contrato():
    """Autenticado mas sem contrato → 400 (fluxo principal de require_contrato)."""
    fake_request = MagicMock()
    fake_request.session = {"user": {"username": "u"}}

    with pytest.raises(HTTPException) as exc_info:
        require_contrato(fake_request)
    assert exc_info.value.status_code == 400
    assert "contrato" in exc_info.value.detail.lower()


def test_require_contrato_returns_id_when_authenticated_and_present():
    fake_request = MagicMock()
    fake_request.session = {"user": {"username": "u"}, "contrato_id": "abc-123"}

    result = require_contrato(fake_request)
    assert result == "abc-123"


# -------- F4 follow-up: nfs_count no /api/contratos --------

def test_list_contratos_includes_nfs_count(client) -> None:
    """`GET /api/contratos` retorna `nfs_count` por contrato via LEFT JOIN."""
    from datetime import date
    from decimal import Decimal
    from app.models import NfEntry

    _seed_contratos([
        _sample_contrato("ECFS A"),
        _sample_contrato("ECFS B"),
        _sample_contrato("ECFS Z"),  # sem nenhuma NF
    ])

    # 3 NFs para A, 1 para B, 1 sem contrato_id (pré-F2 — não deve contar)
    with get_session() as db:
        for i, (numero_nf, cid) in enumerate([
            ("A1", "id-ECFS A"),
            ("A2", "id-ECFS A"),
            ("A3", "id-ECFS A"),
            ("B1", "id-ECFS B"),
            ("LEGADO", None),
        ]):
            db.add(NfEntry(
                business_key=f"bk-{i}-{numero_nf}",
                numero_nf=numero_nf,
                cnpj="00000000000001",
                data_emissao=date(2024, 6, 15),
                tipo_nota="service",
                descricao=f"desc {numero_nf}",
                valor_total=Decimal("100"),
                contrato_id=cid,
                raw_payload={},
            ))
        db.commit()

    authenticate(client)
    response = client.get("/api/contratos")
    assert response.status_code == 200
    data = response.json()
    counts = {c["numero"]: c["nfs_count"] for c in data}
    assert counts == {"ECFS A": 3, "ECFS B": 1, "ECFS Z": 0}, counts


# -------- F3: filtros opcionais em /api/contratos --------

def test_list_contratos_no_params_preserves_regression(client) -> None:
    """Sem params → comportamento atual (todos ativos ordenados por numero)."""
    _seed_contratos([
        _sample_contrato("ECFS 101/2005", uf="SP", tipo_contrato="LPT", tranche="2ª Tranche"),
        _sample_contrato("ECFS 280/2009", uf="AC", tipo_contrato="LPT", tranche="4ª Tranche", sigla="ENERGISA"),
        _sample_contrato("ECM 008/2022", uf="AC", tipo_contrato="MLA", tranche="1ª Tranche", sigla="ENERGISA"),
        _sample_contrato("ECFS 999/1999", ativo=False),
    ])
    authenticate(client)
    response = client.get("/api/contratos")
    data = response.json()
    assert len(data) == 3  # inativo escondido
    assert [c["numero"] for c in data] == sorted([c["numero"] for c in data])


def test_list_contratos_filter_by_numero_ilike(client) -> None:
    _seed_contratos([
        _sample_contrato("ECFS 101/2005"),
        _sample_contrato("ECFS 280/2009"),
        _sample_contrato("ECM 008/2022"),
    ])
    authenticate(client)
    response = client.get("/api/contratos?numero=ECFS")
    data = response.json()
    assert len(data) == 2
    assert all(c["numero"].startswith("ECFS") for c in data)


def test_list_contratos_filter_by_sigla_ilike_case_insensitive(client) -> None:
    _seed_contratos([
        _sample_contrato("ECFS 1", sigla="CPFL"),
        _sample_contrato("ECFS 2", sigla="ENERGISA AC"),
        _sample_contrato("ECFS 3", sigla="energisa rj"),  # minúsculo
    ])
    authenticate(client)
    response = client.get("/api/contratos?sigla=energisa")
    data = response.json()
    assert len(data) == 2, f"esperado 2 (case-insensitive), recebido {len(data)}"


def test_list_contratos_filter_by_uf(client) -> None:
    _seed_contratos([
        _sample_contrato("ECFS 1", uf="SP"),
        _sample_contrato("ECFS 2", uf="SP"),
        _sample_contrato("ECFS 3", uf="AC"),
    ])
    authenticate(client)
    response = client.get("/api/contratos?uf=SP")
    data = response.json()
    assert len(data) == 2


def test_list_contratos_filter_by_tipo_contrato(client) -> None:
    _seed_contratos([
        _sample_contrato("ECFS 1", tipo_contrato="LPT"),
        _sample_contrato("ECFS 2", tipo_contrato="MLA"),
        _sample_contrato("ECFS 3", tipo_contrato="MLA"),
    ])
    authenticate(client)
    response = client.get("/api/contratos?tipo_contrato=MLA")
    data = response.json()
    assert len(data) == 2


def test_list_contratos_com_valor_filter(client) -> None:
    _seed_contratos([
        _sample_contrato("ECFS COM_VALOR", valor_contrato=1000000),
        _sample_contrato("ECFS SEM_VALOR", valor_contrato=0),
    ])
    authenticate(client)
    response = client.get("/api/contratos?com_valor=true")
    data = response.json()
    assert len(data) == 1
    assert data[0]["numero"] == "ECFS COM_VALOR"


def test_list_contratos_incluir_inativos(client) -> None:
    _seed_contratos([
        _sample_contrato("ECFS ATIVO", ativo=True),
        _sample_contrato("ECFS INATIVO", ativo=False),
    ])
    authenticate(client)

    # default — só ativos
    default_resp = client.get("/api/contratos")
    assert len(default_resp.json()) == 1

    # com toggle ligado — ambos
    incl_resp = client.get("/api/contratos?incluir_inativos=true")
    data = incl_resp.json()
    assert len(data) == 2


def test_list_contratos_combination_is_and(client) -> None:
    """Filtros combinados aplicam AND."""
    _seed_contratos([
        _sample_contrato("ECFS 1", uf="SP", tipo_contrato="LPT", valor_contrato=1000),
        _sample_contrato("ECFS 2", uf="SP", tipo_contrato="MLA", valor_contrato=1000),
        _sample_contrato("ECFS 3", uf="AC", tipo_contrato="LPT", valor_contrato=1000),
        _sample_contrato("ECFS 4", uf="SP", tipo_contrato="LPT", valor_contrato=0),
    ])
    authenticate(client)
    response = client.get("/api/contratos?uf=SP&tipo_contrato=LPT&com_valor=true")
    data = response.json()
    assert len(data) == 1
    assert data[0]["numero"] == "ECFS 1"


def test_list_contratos_empty_filter_returns_empty(client) -> None:
    _seed_contratos([_sample_contrato("ECFS 1", uf="SP")])
    authenticate(client)
    response = client.get("/api/contratos?uf=ZZ")
    assert response.status_code == 200
    assert response.json() == []


def test_list_contratos_q_matches_numero_or_sigla(client) -> None:
    """Param `q` faz ILIKE OR em numero e sigla (busca livre)."""
    _seed_contratos([
        _sample_contrato("ECFS 101/2005", sigla="CPFL"),
        _sample_contrato("ECFS 280/2009", sigla="ENERGISA AC"),
        _sample_contrato("ECM 008/2022", sigla="ENERGISA AC"),
        _sample_contrato("ECFS 999/1999", sigla="OUTRO"),
    ])
    authenticate(client)

    # casa por sigla
    r1 = client.get("/api/contratos?q=energisa")
    assert len(r1.json()) == 2

    # casa por numero
    r2 = client.get("/api/contratos?q=ECFS")
    nums = sorted(c["numero"] for c in r2.json())
    assert nums == ["ECFS 101/2005", "ECFS 280/2009", "ECFS 999/1999"]

    # parcial vale para qualquer um dos dois
    r3 = client.get("/api/contratos?q=008")
    assert len(r3.json()) == 1
    assert r3.json()[0]["numero"] == "ECM 008/2022"
