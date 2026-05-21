import os
import json
import logging
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from tqdm import tqdm

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

_CONTEXTO_PATH = "contexto_programa.json"

# Workers do ThreadPoolExecutor. 8 é o padrão conservador para batches de
# até ~550 NFs; se a telemetria não mostrar 429s, dá para subir via env.
# Se 429 começar a dominar, cair para 2-4.
MAX_WORKERS = int(os.getenv("LLM_WORKERS", "8"))

# Mapa modelo -> (preço_in, preço_out) em USD por 1M tokens. Quando o modelo
# atual está mapeado, a telemetria inclui custo estimado em USD. Ausente =
# resumo mostra só tokens. Atualize quando souber o preço.
_PRECOS_USD_POR_1M = {
    # "openai/gpt-oss-120b": (0.00, 0.00),  # preencha quando souber
}


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

    Invariantes do batch:
        - O resultado da linha i sempre volta para a posição i (ordem preservada).
        - Cleaner NUNCA retorna None nem string vazia. Em caso de falha do LLM,
          devolve o texto bruto (sem truncar) e contabiliza em `n_bruto`.
        - Uma falha de uma linha NÃO interrompe o batch — as outras seguem em
          paralelo. ThreadPoolExecutor isola as tarefas.
    """

    _SYSTEM_PRECISAO = (
        "Limpa descrição de Nota Fiscal de obra pública.\n"
        "Contexto do programa: {ctx}\n\n"
        "Sua saída = o texto original SEM o ruído administrativo. "
        "Em dúvida, MANTENHA. Nunca resuma. Nunca retorne vazio.\n\n"
        "MANTENHA:\n"
        "- Descrição do produto/serviço completa, com especificações técnicas "
        "(potência, voltagem, dimensões, modelo, gramatura, cores)\n"
        "- Códigos alfanuméricos do produto (SIGFI, KIT, modelos, séries)\n"
        "- Se houver MÚLTIPLOS itens listados: TODOS eles, na ordem, com suas "
        "descrições, quantidades e valores individuais\n\n"
        "REMOVA:\n"
        "- Prefixo numérico de índice de item (ex.: \"503 KIT...\" → \"KIT...\")\n"
        "- Números de autorização, processo, faturamento, boletim, ordem de serviço\n"
        "- Dados bancários, cálculos fiscais (alíquota, base, ISS, INSS, retenção, dedução)\n"
        "- Texto legal (\"Conforme lei\", \"Art. X\", obrigações tributárias, IR/IRRF)\n"
        "- Datas e condições de pagamento\n\n"
        "EXEMPLO 1: \"503 KIT FOTOVOLTAICO 75KW. Autoriz.230062.\"\n"
        "         → \"KIT FOTOVOLTAICO 75KW\"\n"
        "EXEMPLO 2: \"Autoriz.X. 1.200 Adesivos 40cm VLR:$1,50 / 1.200 Cartilhas VLR:$4.\"\n"
        "         → \"1.200 Adesivos 40cm VLR:$1,50 / 1.200 Cartilhas VLR:$4\""
    )

    _SYSTEM_RECALL = (
        "Limpeza conservadora de descrição de NF. Contexto: {ctx}\n\n"
        "Devolva o texto recebido removendo APENAS ruído inequívoco:\n"
        "- Dados bancários, valores fiscais (ISS, INSS, alíquota, base de cálculo)\n"
        "- Texto legal (artigos, \"Conforme lei\")\n"
        "- Códigos de boletim, autorização, faturamento\n\n"
        "Em qualquer outro caso, MANTENHA. Nunca resuma. Nunca retorne vazio."
    )

    _USER_INDIVIDUAL = "Texto bruto:\n{texto}\n\nDevolva apenas o texto limpo."

    _USER_FALLBACK = (
        "Texto bruto:\n{texto}\n\n"
        "Devolva todo o conteúdo descritivo de produto/serviço presente, "
        "preservando todos os itens listados. Nunca retorne vazio."
    )

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
        # Telemetria — Counter sob lock porque threads incrementam concorrentemente.
        self._metrics = Counter()
        self._metrics_lock = threading.Lock()
        self._tempo_total = 0.0

    # ------------------------------------------------------------------ #
    #  API pública                                                         #
    # ------------------------------------------------------------------ #

    def batch_clean(self, df, modo: str):
        """
        Limpa a coluna 'descricao' do df completo, em paralelo.
        Chamado uma vez após o laço de PDFs, antes do to_excel().
        """
        if not self._api_key:
            logger.warning("OPENROUTER_API_KEY ausente. Coluna descricao não será limpa.")
            return df

        textos = df['descricao'].tolist()
        n = len(textos)
        if n == 0:
            return df.copy()

        # Pré-alocado para preservar ordem: limpos[i] vai para df.iloc[i].
        limpos = [None] * n

        self._reset_metrics()
        inicio = time.monotonic()

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = {ex.submit(self._call_item, texto, modo): i for i, texto in enumerate(textos)}
            with tqdm(total=n, desc="LLM clean", unit="item", ncols=90) as pbar:
                for fut in as_completed(futures):
                    i = futures[fut]
                    try:
                        limpos[i] = fut.result()
                    except Exception as e:
                        # Defesa em profundidade — _call_item NÃO deveria
                        # propagar exceção. Se acontecer, conta e usa bruto.
                        logger.error("_call_item exceção escapou na linha %d: %s", i, e)
                        self._inc('n_excecao_escapou')
                        bruto = textos[i] if textos[i] else ""
                        limpos[i] = bruto.strip() or bruto
                    pbar.update(1)

        self._tempo_total = time.monotonic() - inicio
        self._registrar_resumo(n)

        df = df.copy()
        df['descricao'] = limpos
        return df

    def clean(self, texto_bruto: str, modo: str) -> str:
        """Limpeza individual — mantido para uso standalone e testes.

        Mesmas garantias do batch: nunca retorna None nem vazio; falha vira
        texto bruto. Não acumula telemetria (uso esparso).
        """
        if not self._api_key:
            logger.warning("OPENROUTER_API_KEY ausente. Retornando texto bruto.")
            return texto_bruto
        return self._call_item(texto_bruto, modo)

    # ------------------------------------------------------------------ #
    #  Internals                                                           #
    # ------------------------------------------------------------------ #

    def _call_item(self, texto: str, modo: str) -> str:
        """
        Envia uma descrição ao LLM e retorna a descrição limpa.
        Cascata: tentativa principal → fallback recall → texto bruto.

        Garantias:
          - Nunca retorna None nem string vazia (se `texto` chegar não-vazio).
          - Nunca lança exceção — qualquer falha vira texto bruto contabilizado.
          - Não trunca o input.
        """
        try:
            system = self._build_system_prompt(modo)
            resultado = self._sanitize(
                self._call_llm(system, self._USER_INDIVIDUAL.format(texto=texto))
            )
            if resultado:
                return resultado

            # Fallback recall — segunda tentativa antes de desistir.
            self._inc('n_fallback_recall')
            resultado = self._sanitize(
                self._call_llm(self._build_system_prompt("recall"),
                               self._USER_FALLBACK.format(texto=texto))
            )
            if resultado:
                return resultado
        except Exception as e:
            logger.warning("_call_item exceção: %s", e)
            self._inc('n_excecao_interna')

        # Última linha de defesa: bruto sem truncar.
        self._inc('n_bruto')
        return texto.strip() or texto

    def _call_llm(self, system_prompt: str, user_prompt: str):
        """Faz um POST ao endpoint de chat. Retorna o conteúdo da resposta
        ou None em falha. Backoff só no 429; outras exceções não tentam de novo.
        """
        self._inc('n_calls_llm')
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            # 4000 cobre o long tail real (NFs multi-item com dezenas de
            # produtos podem precisar de 1.500-3.800 tokens de output limpo).
            # 300 era pequeno demais — induzia o LLM a desistir/cuspir bruto
            # em inputs longos. gpt-oss-120b tem contexto bem maior, não há
            # risco de limite do modelo. Cobra-se apenas pelo uso real.
            "max_tokens": 4000,
            "temperature": 0.0,
        }
        for attempt in range(2):
            try:
                response = self._session.post(self._url, json=payload, timeout=20)
                if response.status_code == 429:
                    self._inc('n_429')
                    wait = 10 * (attempt + 1)
                    logger.warning("429 rate limit. Aguardando %ds (tentativa %d).", wait, attempt + 1)
                    time.sleep(wait)
                    continue
                response.raise_for_status()
                data = response.json()
                usage = data.get("usage", {})
                tok_in = usage.get("prompt_tokens")
                tok_out = usage.get("completion_tokens")
                if isinstance(tok_in, int) and isinstance(tok_out, int):
                    with self._metrics_lock:
                        self._metrics['tokens_in'] += tok_in
                        self._metrics['tokens_out'] += tok_out
                return data["choices"][0]["message"]["content"]
            except Exception as e:
                logger.warning("_call_llm exceção: %s", e)
                self._inc('n_http_falhas')
                return None
        # Loop terminou sem retorno → 429 esgotou todas as tentativas.
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

    # ------------------------------------------------------------------ #
    #  Telemetria                                                          #
    # ------------------------------------------------------------------ #

    def _reset_metrics(self):
        with self._metrics_lock:
            self._metrics.clear()

    def _inc(self, name: str, valor: int = 1):
        with self._metrics_lock:
            self._metrics[name] += valor

    def _registrar_resumo(self, n_linhas: int):
        """Imprime resumo no terminal e anexa entrada estruturada em log.json."""
        m = self._metrics
        tempo = max(self._tempo_total, 0.001)  # evita divisão por zero
        taxa = n_linhas / tempo

        preco = _PRECOS_USD_POR_1M.get(self._model)
        if preco:
            in_usd, out_usd = preco
            custo = (m['tokens_in'] / 1e6) * in_usd + (m['tokens_out'] / 1e6) * out_usd
            custo_linha = f"  custo estimado     : USD {custo:.4f}\n"
        else:
            custo = None
            custo_linha = ""

        resumo = (
            f"\n[LLM cleaner] modelo={self._model} workers={MAX_WORKERS}\n"
            f"  linhas             : {n_linhas}\n"
            f"  chamadas LLM (POST): {m['n_calls_llm']}\n"
            f"  fallback recall    : {m['n_fallback_recall']}\n"
            f"  retorno bruto      : {m['n_bruto']}\n"
            f"  429 rate-limit     : {m['n_429']}\n"
            f"  falhas HTTP        : {m['n_http_falhas']}\n"
            f"  exceção interna    : {m['n_excecao_interna']}\n"
            f"  exceção escapou    : {m['n_excecao_escapou']}\n"
            f"  tokens in / out    : {m['tokens_in']:,} / {m['tokens_out']:,}\n"
            f"{custo_linha}"
            f"  tempo total        : {tempo:.1f}s ({taxa:.1f} linhas/s)\n"
        )
        print(resumo)

        log = {
            'tipo': 'resumo_llm',
            'modelo': self._model,
            'workers': MAX_WORKERS,
            'linhas': n_linhas,
            'chamadas_llm': m['n_calls_llm'],
            'fallback_recall': m['n_fallback_recall'],
            'retorno_bruto': m['n_bruto'],
            'n_429': m['n_429'],
            'falhas_http': m['n_http_falhas'],
            'excecao_interna': m['n_excecao_interna'],
            'excecao_escapou': m['n_excecao_escapou'],
            'tokens_in': m['tokens_in'],
            'tokens_out': m['tokens_out'],
            'tempo_seg': round(tempo, 2),
        }
        if custo is not None:
            log['custo_usd'] = round(custo, 4)

        try:
            with open("log.json", "a", encoding="utf-8") as f:
                f.write(json.dumps(log, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.warning("não foi possível anexar resumo ao log.json: %s", e)


cleaner = DescriptionCleaner(
    contexto_path=_CONTEXTO_PATH,
    api_key=os.getenv("OPENROUTER_API_KEY", ""),
    model_id=os.getenv("OPENROUTER_MODEL", "openai/gpt-oss-120b"),
)
