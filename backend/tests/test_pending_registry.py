"""F8b — testes do pending_registry (asyncio.Event registry in-memory)."""
import asyncio

import pytest

from app import pending_registry


@pytest.fixture(autouse=True)
def _reset_registry():
    """Limpa o registry entre testes — globals mutáveis precisam de
    cleanup explícito."""
    pending_registry._events.clear()
    pending_registry._desfechos.clear()
    yield
    pending_registry._events.clear()
    pending_registry._desfechos.clear()


def test_register_cria_event_novo_e_desfecho_default():
    event = pending_registry.register("p-1")
    assert isinstance(event, asyncio.Event)
    assert not event.is_set()

    desfecho = pending_registry._desfechos["p-1"]
    assert desfecho.resolved is False
    assert desfecho.cancelled is False


def test_signal_resolve_marca_desfecho_e_seta_event():
    event = pending_registry.register("p-2")

    ok = pending_registry.signal_resolve("p-2")
    assert ok is True
    assert event.is_set()
    assert pending_registry._desfechos["p-2"].resolved is True


def test_signal_cancel_marca_desfecho_e_seta_event():
    event = pending_registry.register("p-3")

    ok = pending_registry.signal_cancel("p-3")
    assert ok is True
    assert event.is_set()
    assert pending_registry._desfechos["p-3"].cancelled is True


def test_signal_resolve_em_pendencia_desconhecida_retorna_false():
    """Race: /resolve chegou após consume_desfecho. Não é erro — endpoint
    transforma em 409 com a NF já tendo sido inserida ou não."""
    assert pending_registry.signal_resolve("p-unknown") is False


def test_signal_cancel_em_pendencia_desconhecida_retorna_false():
    assert pending_registry.signal_cancel("p-unknown") is False


def test_consume_desfecho_remove_entrada_do_registry():
    pending_registry.register("p-4")
    pending_registry.signal_resolve("p-4")

    desfecho = pending_registry.consume_desfecho("p-4")
    assert desfecho.resolved is True
    assert "p-4" not in pending_registry._events
    assert "p-4" not in pending_registry._desfechos


def test_consume_desfecho_de_pendencia_inexistente_retorna_default():
    """Cobre o caso de timeout sem signal — generator chama consume e
    recebe desfecho default (resolved=False, cancelled=False). Caller
    trata como cancel implícito."""
    desfecho = pending_registry.consume_desfecho("p-never-registered")
    assert desfecho.resolved is False
    assert desfecho.cancelled is False


def test_has_pending_distingue_aguardando_de_consumido():
    pending_registry.register("p-5")
    assert pending_registry.has_pending("p-5") is True

    pending_registry.consume_desfecho("p-5")
    assert pending_registry.has_pending("p-5") is False


def test_register_idempotente_preserva_event_mas_reseta_desfecho():
    """Cenário raro: registry é chamado duas vezes pro mesmo id (retry
    interno). Não pode acordar futures de uma chamada anterior — reusa
    o Event mas zera o desfecho."""
    event1 = pending_registry.register("p-6")
    pending_registry._desfechos["p-6"].resolved = True

    event2 = pending_registry.register("p-6")
    assert event1 is event2  # mesmo Event
    assert pending_registry._desfechos["p-6"].resolved is False  # desfecho zerado


# Nota: a coordenação async real (generator awaiting event + endpoint
# signal_resolve acordando) é exercitada no teste e2e da Fase B3b. Aqui
# os 9 testes acima cobrem a API do registry — asyncio.Event é primitiva
# stdlib confiável, não precisa de unit test isolado.
