import hashlib
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation


def normalize_text(value: object) -> str:
    text = "" if value is None else str(value)
    return " ".join(text.split()).strip()


def normalize_nullable_text(value: object) -> str | None:
    text = normalize_text(value)
    return text or None


def normalize_cnpj(value: object) -> str:
    return re.sub(r"\D", "", normalize_text(value))


def parse_brazilian_date(value: object):
    text = normalize_text(value)
    match = re.search(r"\b\d{2}/\d{2}/\d{4}\b", text)
    if not match:
        raise ValueError(f"Data invalida: {text}")

    return datetime.strptime(match.group(0), "%d/%m/%Y").date()


def parse_brazilian_decimal(value: object) -> Decimal | None:
    text = normalize_text(value)
    if not text:
        return None

    sanitized = text.replace(".", "").replace(",", ".")
    try:
        return Decimal(sanitized)
    except InvalidOperation:
        return None


class NfRowValidationError(ValueError):
    """Campo numérico obrigatório de uma linha de NF ausente ou ilegível no
    retorno do parser. Subclasse de ValueError — capturada pelo `except`
    per-file do upload, que marca o arquivo como `erro_parsing` com motivo
    claro. Ver docs/BUG_validacao_numerica_pre_insert.md."""


def parse_required_decimal(value: object, field_name: str) -> Decimal:
    """Converte um campo numérico obrigatório (formato BR) para Decimal.

    Diferente de `parse_brazilian_decimal` — que devolve None em falha — esta
    levanta `NfRowValidationError` nomeando o campo. Assim o upload trata o
    dado malformado como `erro_parsing` em vez de gravar `0` silencioso
    (corrupção) ou `None` (que viola o `NOT NULL` dentro do `flush()`)."""
    parsed = parse_brazilian_decimal(value)
    if parsed is None:
        raise NfRowValidationError(
            f"Campo numérico obrigatório '{field_name}' ausente ou ilegível "
            f"(valor recebido do parser: {value!r})."
        )
    return parsed


def build_business_key(row: dict) -> str:
    numero_nf = normalize_text(row.get("numero_nf"))
    cnpj = normalize_cnpj(row.get("cnpj"))
    data_emissao = parse_brazilian_date(row.get("data_emissao")).isoformat()
    valor_total = parse_brazilian_decimal(row.get("valor"))
    descricao = normalize_text(row.get("descricao")).upper()

    return "|".join(
        [
            numero_nf,
            cnpj,
            data_emissao,
            f"{valor_total:.2f}" if valor_total is not None else "",
            descricao,
        ]
    )


def compute_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
