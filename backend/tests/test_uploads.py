from pathlib import Path

from app.parser_adapter import ParserOutcome


def authenticate(client) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "user", "password": "password"},
    )
    assert response.status_code == 200


def test_upload_requires_authentication(client) -> None:
    response = client.post(
        "/api/uploads",
        files=[("files", ("nota.pdf", b"fake-pdf", "application/pdf"))],
    )

    assert response.status_code == 401


def test_upload_rejects_non_pdf(client) -> None:
    authenticate(client)

    response = client.post(
        "/api/uploads",
        files=[("files", ("arquivo.txt", b"abc", "text/plain"))],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["files"][0]["status"] == "rejeitado"


def test_upload_persists_new_rows_and_lists_entries(client, monkeypatch) -> None:
    authenticate(client)

    class FakeAdapter:
        def parse_pdf_bytes(self, filename: str, content: bytes):
            return ParserOutcome(
                status="processado",
                rows=[
                    {
                        "descricao": "Servico de instalacao",
                        "ncm": "não se aplica",
                        "quant": 1,
                        "preco_unitario": "5656,23",
                        "numero_nf": "123",
                        "tipo_nota": "service",
                        "data_emissao": "03/10/2024",
                        "cnpj": "01.126.556/0001-91",
                        "fornecedor": "Fornecedor Teste",
                        "valor": "5656,23",
                        "contrato": "ECM-023-2025",
                    }
                ],
            )

    monkeypatch.setattr("app.main.LegacyParserAdapter", FakeAdapter)

    response = client.post(
        "/api/uploads",
        files=[("files", ("nota.pdf", b"fake-pdf", "application/pdf"))],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["files"][0]["status"] == "processado"
    assert payload["files"][0]["inserted_count"] == 1
    saved_path = Path(payload["files"][0]["saved_path"])
    assert saved_path.exists()
    assert saved_path.read_bytes() == b"fake-pdf"

    entries_response = client.get("/api/nf-entries")
    assert entries_response.status_code == 200
    entries = entries_response.json()
    assert len(entries) == 1
    assert entries[0]["numero_nf"] == "123"
    assert entries[0]["valor_total"] == "5656,23"


def test_upload_list_preserves_raw_parser_fields(client, monkeypatch) -> None:
    authenticate(client)

    class FakeAdapter:
        def parse_pdf_bytes(self, filename: str, content: bytes):
            return ParserOutcome(
                status="processado",
                rows=[
                    {
                        "descricao": "Servico com lixo visual",
                        "ncm": "n/a",
                        "quant": "1,0000",
                        "preco_unitario": "5656,23",
                        "numero_nf": "123-A",
                        "tipo_nota": "service",
                        "data_emissao": "03/10/2024 -",
                        "cnpj": "01.126.556/0001-91",
                        "fornecedor": "Fornecedor Teste",
                        "valor": "5656,23",
                        "contrato": "ECM-023-2025",
                    }
                ],
            )

    monkeypatch.setattr("app.main.LegacyParserAdapter", FakeAdapter)

    response = client.post(
        "/api/uploads",
        files=[("files", ("nota.pdf", b"fake-pdf", "application/pdf"))],
    )

    assert response.status_code == 200

    entries_response = client.get("/api/nf-entries")
    assert entries_response.status_code == 200
    entries = entries_response.json()
    assert entries[0]["data_emissao"] == "03/10/2024 -"
    assert entries[0]["valor_total"] == "5656,23"
    assert entries[0]["quantidade"] == "1,0000"


def test_upload_marks_duplicate_when_rows_already_exist(client, monkeypatch) -> None:
    authenticate(client)

    class FakeAdapter:
        def parse_pdf_bytes(self, filename: str, content: bytes):
            return ParserOutcome(
                status="processado",
                rows=[
                    {
                        "descricao": "Servico de instalacao",
                        "ncm": "não se aplica",
                        "quant": 1,
                        "preco_unitario": "5656,23",
                        "numero_nf": "123",
                        "tipo_nota": "service",
                        "data_emissao": "03/10/2024",
                        "cnpj": "01.126.556/0001-91",
                        "fornecedor": "Fornecedor Teste",
                        "valor": "5656,23",
                        "contrato": "ECM-023-2025",
                    }
                ],
            )

    monkeypatch.setattr("app.main.LegacyParserAdapter", FakeAdapter)

    first = client.post(
        "/api/uploads",
        files=[("files", ("nota.pdf", b"fake-pdf", "application/pdf"))],
    )
    assert first.status_code == 200

    second = client.post(
        "/api/uploads",
        files=[("files", ("nota-duplicada.pdf", b"fake-pdf", "application/pdf"))],
    )
    assert second.status_code == 200
    payload = second.json()
    assert payload["files"][0]["status"] == "duplicado"
    assert payload["files"][0]["duplicate_count"] == 1
    assert Path(payload["files"][0]["saved_path"]).exists()


def test_upload_batch_details_endpoint_returns_file_statuses(client, monkeypatch) -> None:
    authenticate(client)

    class FakeAdapter:
        def parse_pdf_bytes(self, filename: str, content: bytes):
            return ParserOutcome(status="rejeitado", rows=[], reason="Arquivo incompatível.")

    monkeypatch.setattr("app.main.LegacyParserAdapter", FakeAdapter)

    response = client.post(
        "/api/uploads",
        files=[("files", ("nota.pdf", b"fake-pdf", "application/pdf"))],
    )
    assert response.status_code == 200
    batch_id = response.json()["batch_id"]

    details = client.get(f"/api/upload-batches/{batch_id}")
    assert details.status_code == 200
    payload = details.json()
    assert payload["files"][0]["status"] == "rejeitado"
