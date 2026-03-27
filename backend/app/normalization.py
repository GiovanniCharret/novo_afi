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
    return datetime.strptime(normalize_text(value), "%d/%m/%Y").date()


def parse_brazilian_decimal(value: object) -> Decimal | None:
    text = normalize_text(value)
    if not text:
        return None

    sanitized = text.replace(".", "").replace(",", ".")
    try:
        return Decimal(sanitized)
    except InvalidOperation:
        return None


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
