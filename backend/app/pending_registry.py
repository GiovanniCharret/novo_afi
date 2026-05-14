"""F8b — registry in-memory de asyncio.Event por nf_pending_id.

Vida útil curta: um Event é criado pelo SSE generator quando emite
`file_pending_input` e é setado pelo endpoint /resolve ou /cancel
(ou pelo timeout interno do generator). Após `consume_desfecho`, a
entrada é removida do registry.

Por que in-memory (não DB ou Redis):
- O Event é uma primitiva de sincronização entre duas tasks do MESMO
  processo Python (o generator awaiting + a request resolve/cancel
  acordando o generator). Persistir não ajudaria — se o processo cai,
  o generator não retoma de qualquer jeito.
- Cross-reboot: pendings continuam no DB (`nf_pending` com status
  'aguardando'). Job de startup (B3b) varre rows com `expires_at < now()`
  e marca como expirado, fechando o ciclo sem precisar do Event.
- Multi-processo / múltiplas réplicas: hoje o backend é mono-réplica.
  Quando virar multi, este registry vira insuficiente — substituir por
  pub/sub (Redis Streams) ou repensar o fluxo. Documentado.

Thread/coroutine safety: dict do CPython é thread-safe para operações
atômicas individuais (`get`, `set`, `pop`). Não há contenção entre
generator e endpoint porque cada `nf_pending_id` é único — só um
caller escreve, só um caller lê.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass
class PendingDesfecho:
    """Resultado de uma pendência. Lido pelo generator após event.wait()."""
    resolved: bool = False
    cancelled: bool = False


_events: dict[str, asyncio.Event] = {}
_desfechos: dict[str, PendingDesfecho] = {}


def register(nf_pending_id: str) -> asyncio.Event:
    """Cria um Event novo para esta pendência. Chamado pelo generator.

    Idempotente — se já existe (caso raro de retry), reseta o desfecho
    mas reusa o Event para evitar acordar futures antigas.
    """
    if nf_pending_id not in _events:
        _events[nf_pending_id] = asyncio.Event()
    _desfechos[nf_pending_id] = PendingDesfecho()
    return _events[nf_pending_id]


def signal_resolve(nf_pending_id: str) -> bool:
    """Marca como resolvido e acorda o generator. Chamado pelo /resolve.

    Retorna True se sinalizou; False se a pendência não está mais no
    registry (timeout/cancel já consumiu, ou /resolve chegou depois do
    expirou). Não é erro — só sinal pro endpoint responder 409.
    """
    if nf_pending_id not in _events:
        return False
    _desfechos[nf_pending_id].resolved = True
    _events[nf_pending_id].set()
    return True


def signal_cancel(nf_pending_id: str) -> bool:
    """Marca como cancelado e acorda o generator. Chamado pelo /cancel
    ou pelo próprio generator no timeout interno.
    """
    if nf_pending_id not in _events:
        return False
    _desfechos[nf_pending_id].cancelled = True
    _events[nf_pending_id].set()
    return True


def consume_desfecho(nf_pending_id: str) -> PendingDesfecho:
    """Lê desfecho e remove a entrada do registry. Chamado pelo generator
    após event.wait().

    Se não existe (caso de timeout sem ninguém ter chamado signal_*),
    retorna PendingDesfecho default (`resolved=False, cancelled=False`).
    """
    _events.pop(nf_pending_id, None)
    return _desfechos.pop(nf_pending_id, PendingDesfecho())


def has_pending(nf_pending_id: str) -> bool:
    """Util pros endpoints: pendência ainda está aguardando ação?

    True só enquanto o generator está em `await event.wait()`. Após
    `consume_desfecho`, vira False — útil pra distinguir 'já resolvido'
    de 'expirou e generator fechou'.
    """
    return nf_pending_id in _events


# ---------------------------------------------------------------------------
# Recovery cross-reboot (counterpart persistente do registry in-memory)
#
# O registry acima é totalmente em memória — morre com o processo. Pendings
# que estavam aguardando quando o servidor caiu ficam órfãos: a row em
# `nf_pending` continua com status='aguardando', mas não há generator algum
# esperando pelo Event. O job abaixo roda no startup do lifespan e fecha
# essas pendências marcando-as como expirado quando `expires_at < now()`.
# ---------------------------------------------------------------------------

def expire_orphan_pendings(db) -> int:
    """F8b — fecha pendings órfãos cross-reboot.

    Critério: `status='aguardando' AND expires_at < now()`. Razão da
    intersecção (em vez de expirar todo 'aguardando'): pendência criada
    pouco antes do crash, dentro da janela de 30min, ainda pode receber
    /resolve legítimo após o reboot. Forçar expirar imediatamente quebraria
    esse caminho. Quem está dentro da janela continua 'aguardando' até o
    operador retomar ou o tempo acabar; quem já passou da janela é
    invariavelmente órfão.

    Atualiza também `upload_files.status` da pendência associada para
    `rejeitado_pendencia_expirada`, liberando o painel de status. Idempotente
    — segundas chamadas não fazem nada porque o WHERE já filtrou.

    Retorna a contagem de pendências expiradas (para log de startup).

    O caller passa o `Session`. Não importa models aqui — import local pra
    evitar ciclo com `pending_registry` sendo importado em models/server.
    """
    from datetime import datetime, timezone
    from sqlalchemy import select
    from .models import NfPending, UploadFile

    now = datetime.now(timezone.utc)
    orphans = db.scalars(
        select(NfPending).where(
            NfPending.status == "aguardando",
            NfPending.expires_at < now,
        )
    ).all()

    count = 0
    for pending in orphans:
        pending.status = "expirado"
        pending.resolved_at = now
        upload_file = db.get(UploadFile, pending.upload_file_id)
        if upload_file is not None and upload_file.status == "aguardando_preenchimento":
            upload_file.status = "rejeitado_pendencia_expirada"
            upload_file.status_reason = "Pendência expirou (recovery cross-reboot)."
        count += 1

    if count:
        db.commit()
    return count
