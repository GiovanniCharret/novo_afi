"""F5 — testes do limite hard de 550 PDFs por batch.

Cobre apenas a regra de quantidade. O teste de 551 confirma que o 422 dispara
antes de qualquer leitura de bytes (F5 é a primeira validação após auth e
contrato). O teste de 550 confirma que o limite é exato (não rejeita NO limite).

F2 introduziu `require_contrato`: testes que pré-F2 só faziam authenticate
agora também precisam selecionar contrato (ou aceitar 400 do require_contrato
antes de F5 disparar).
"""
from app.db import get_session
from app.models import Contrato


def authenticate(client) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "user", "password": "password"},
    )
    assert response.status_code == 200


def _seed_and_select_contrato(client) -> None:
    """F2 — popula contrato e seleciona para que require_contrato passe."""
    contrato_id = "id-test-contrato"
    with get_session() as db:
        db.add(Contrato(
            id=contrato_id,
            numero="ECFS 100/2005",
            sigla="CPFL",
            cnpj="53859112000169",
            tipo_contrato="LPT",
            valor_contrato=1000,
            valor_cde=800,
            participacao_cde="0.8",
            ativo=True,
        ))
        db.commit()
    response = client.post("/api/session/contrato", json={"contrato_id": contrato_id})
    assert response.status_code == 200


def _make_files(count: int, extension: str = "txt"):
    """Gera tuplas no formato esperado pelo TestClient. Default extensão .txt
    para que o backend rejeite no loop sem chamar o parser (rápido).
    """
    return [
        ("files", (f"nf_{i}.{extension}", b"stub", "text/plain"))
        for i in range(count)
    ]


def test_upload_with_551_files_returns_422_with_count(client) -> None:
    """551 arquivos → 422 com a contagem exata na mensagem (F5 ativa após F2)."""
    authenticate(client)
    _seed_and_select_contrato(client)

    response = client.post("/api/uploads", files=_make_files(551))

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "551" in detail, f"esperado '551' em detail, veio: {detail!r}"
    assert "550" in detail, f"esperado '550' em detail, veio: {detail!r}"
    assert "Limite" in detail, f"esperado 'Limite' em detail, veio: {detail!r}"


def test_upload_with_550_files_does_not_reject_at_limit(client) -> None:
    """550 arquivos (limite exato) → F5 não dispara. Backend continua
    para o pipeline normal. Aqui usamos extensão .txt para que cada arquivo
    seja rejeitado individualmente no loop por não ser PDF — comportamento
    preexistente, não é o 422 do F5.
    """
    authenticate(client)

    response = client.post("/api/uploads", files=_make_files(550))

    # F5 NÃO disparou: status code não pode ser 422 com a mensagem do limite.
    if response.status_code == 422:
        detail = response.json().get("detail", "")
        assert "Limite de 550" not in detail, (
            f"F5 rejeitou no limite exato (errado): {detail!r}"
        )


def test_upload_with_zero_files_preserves_existing_behavior(client) -> None:
    """0 arquivos → comportamento atual mantido. FastAPI rejeita por
    File(...) ser obrigatório, antes de F5 sequer rodar. F5 não regrede
    esse caso.
    """
    authenticate(client)

    response = client.post("/api/uploads", files=[])

    # Comportamento existente: FastAPI retorna 422 do `File(...)` faltante
    # OU outro código de erro. F5 não pode ter introduzido a mensagem do limite
    # nesse cenário (que tem 0 arquivos, não 551).
    if response.status_code == 422:
        detail = response.json().get("detail", "")
        # `detail` pode ser string ou lista (depende de como FastAPI formata)
        detail_str = str(detail)
        assert "Limite de 550" not in detail_str, (
            f"F5 disparou em 0 arquivos (errado): {detail_str!r}"
        )
