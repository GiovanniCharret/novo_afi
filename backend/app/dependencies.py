"""Dependencies do FastAPI compartilhadas entre endpoints.

`require_contrato`: lê `request.session["contrato_id"]`. Se ausente, levanta
`HTTPException(400)`. Endpoints que precisam de contrato selecionado fazem
`Depends(require_contrato)` e recebem o `contrato_id` já validado.

Decisão #9 (PLAN.md): backend retorna 400, frontend faz redirect para
`/contratos`. O 400 é rede de segurança contra estado inconsistente — o
fluxo principal é frontend chamar `GET /api/session/contrato` no boot e
redirecionar antes que o usuário sequer chegue em endpoints protegidos.
"""
from fastapi import HTTPException, Request, status


def require_contrato(request: Request) -> str:
    """Retorna `contrato_id` da sessão. Levanta 401 sem auth, 400 sem contrato.

    Ordem importa: auth precede contrato. Sem essa precedência, requisições
    não-autenticadas receberiam 400 ("contrato ausente") quando o correto
    é 401 ("not authenticated") — adversarial #4 + DoD critério "sem auth → 401".
    """
    if not request.session.get("user"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    contrato_id = request.session.get("contrato_id")
    if not contrato_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nenhum contrato selecionado.",
        )
    return contrato_id
