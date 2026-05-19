import os
import json
import logging
import time
import requests
from tqdm import tqdm

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

_CONTEXTO_PATH = "contexto_programa.json"


def _load_context(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("contexto_programa.json não encontrado. LLM operará sem contexto.")
        return {}
    except json.JSONDecodeError as e:
        logger.warning("contexto_programa.json malformado: %s", e)
        return {}


class DescriptionCleaner:
    """
    Limpa a coluna `descricao` de Notas Fiscais via LLM (OpenRouter).

    Uso principal: batch_clean(df, modo) — chamado uma vez após o laço de PDFs.
    Uso standalone: clean(texto, modo) — para testes pontuais.

    Modos:
        "precisao" — extrai só o núcleo semântico.
        "recall"   — extrai o máximo possível, remove só ruído fiscal óbvio.
    """

    _SYSTEM_PRECISAO = "NF de obras públicas. Contexto: {ctx}\nExtraia só o objeto do serviço/produto. Remova dados fiscais, bancários e legais. Se nada restar, retorne string vazia."

    _SYSTEM_RECALL = "NF de obras públicas. Contexto: {ctx}\nExtraia a descrição mais completa do serviço/produto. Remova só dados claramente fiscais. Nunca retorne vazio."

    _USER_INDIVIDUAL = "NF:\n{texto}\nRetorne só o texto limpo."

    _USER_FALLBACK = "NF com ruído:\n{texto}\nExtraia qualquer descrição de produto/serviço. Nunca retorne vazio."

    def __init__(self, contexto_path, api_key, model_id):
        # Contexto compacto (sem indent) para economizar tokens
        self._ctx_str = json.dumps(
            _load_context(contexto_path),
            ensure_ascii=False,
        )
        self._api_key = api_key
        self._model = model_id
        self._url = "https://openrouter.ai/api/v1/chat/completions"
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })

    _MAX_INPUT_CHARS = 1500

    # ------------------------------------------------------------------ #
    #  API pública                                                         #
    # ------------------------------------------------------------------ #

    # Intervalo entre chamadas para evitar rate limit (segundos).
    _CALL_INTERVAL = 0.5

    def batch_clean(self, df, modo: str):
        """
        Limpa a coluna 'descricao' do df completo, item a item.
        Chamado uma vez após o laço de PDFs, antes do to_excel().
        Todos os valores em 'descricao' devem ser strings — None indica
        falha crítica de extração e não deve chegar aqui.
        """
        if not self._api_key:
            logger.warning("OPENROUTER_API_KEY ausente. Coluna descricao não será limpa.")
            return df

        textos = df['descricao'].tolist()
        limpos = []

        with tqdm(textos, desc="LLM clean", unit="item", ncols=90) as pbar:
            for i, texto in enumerate(pbar):
                chars_in = len(texto)
                pbar.set_postfix(chars_in=chars_in, status="enviando")
                resultado = self._call_item(texto, modo)
                limpos.append(resultado)
                pbar.set_postfix(chars_in=chars_in, chars_out=len(resultado), status="ok")
                time.sleep(self._CALL_INTERVAL)

        df = df.copy()
        df['descricao'] = limpos
        return df

    def clean(self, texto_bruto: str, modo: str) -> str:
        """Limpeza individual — mantido para uso standalone e testes."""
        if not self._api_key:
            logger.warning("OPENROUTER_API_KEY ausente. Retornando texto bruto.")
            return texto_bruto

        texto = texto_bruto[:self._MAX_INPUT_CHARS]
        system = self._build_system_prompt(modo)

        resultado = self._sanitize(
            self._call_llm(system, self._USER_INDIVIDUAL.format(texto=texto))
        )
        if resultado:
            return resultado

        resultado = self._sanitize(
            self._call_llm(self._build_system_prompt("recall"), self._USER_FALLBACK.format(texto=texto))
        )
        if resultado:
            return resultado

        return texto_bruto[:300].strip()

    # ------------------------------------------------------------------ #
    #  Internals                                                           #
    # ------------------------------------------------------------------ #

    def _call_item(self, texto: str, modo: str) -> str:
        """
        Envia um único item ao LLM e retorna a descrição limpa.
        Fallback: tenta com recall; se ainda falhar, retorna texto bruto truncado.
        Nunca retorna None.
        """
        texto = texto[:self._MAX_INPUT_CHARS]
        system = self._build_system_prompt(modo)

        resultado = self._sanitize(
            self._call_llm(system, self._USER_INDIVIDUAL.format(texto=texto))
        )
        if resultado:
            return resultado

        resultado = self._sanitize(
            self._call_llm(self._build_system_prompt("recall"), self._USER_FALLBACK.format(texto=texto))
        )
        if resultado:
            return resultado

        return texto[:300].strip()

    def _call_llm(self, system_prompt: str, user_prompt: str):
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": 300,
            "temperature": 0.0,
        }
        for attempt in range(2):
            try:
                response = self._session.post(self._url, json=payload, timeout=20)
                if response.status_code == 429:
                    wait = 10 * (attempt + 1)
                    tqdm.write(f"  ⚠ 429 rate limit. Aguardando {wait}s...")
                    time.sleep(wait)
                    continue
                response.raise_for_status()
                data = response.json()
                usage = data.get("usage", {})
                tok_in = usage.get("prompt_tokens", "?")
                tok_out = usage.get("completion_tokens", "?")
                tqdm.write(f"  tokens: in={tok_in} out={tok_out}")
                return data["choices"][0]["message"]["content"]
            except Exception as e:
                tqdm.write(f"  ✗ falhou: {e}")
                return None
        return None

    def _build_system_prompt(self, modo: str) -> str:
        template = self._SYSTEM_PRECISAO if modo == "precisao" else self._SYSTEM_RECALL
        return template.format(ctx=self._ctx_str)

    def _sanitize(self, resposta) -> str:
        if not resposta:
            return ""
        texto = resposta.strip().strip('"').strip("'").strip()
        if texto.upper() in {"VAZIO", "N/A", "NA", "NONE", "-"}:
            return ""
        return texto


cleaner = DescriptionCleaner(
    contexto_path=_CONTEXTO_PATH,
    api_key=os.getenv("OPENROUTER_API_KEY", ""),
    model_id=os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-120b"),
)
