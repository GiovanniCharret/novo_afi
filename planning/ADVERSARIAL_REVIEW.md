
# Adversarial Review

Este documento revisa `planning/` como um adversario maximamente competente: procura ambiguidades, lacunas semanticas e formulacoes suaves que permitiriam cumprir tecnicamente a regra enquanto se viola seu espirito.

## 1. "Nao iniciar implementacao antes da aprovacao do dono" sem definicao de aprovacao

**Brecha:** `PLAN.md` proibe iniciar implementacao antes da aprovacao do dono, mas nao define formato, escopo ou registro dessa aprovacao.

**Caminho de exploracao:** assumir que qualquer pedido informal no chat equivale a aprovacao total do roadmap e iniciar F1-F8 sem registrar quais decisoes foram aprovadas.

**Endurecimento:** exigir aprovacao explicita por feature, registrada em `planning/PLAN.md` ou issue/PR: "Aprovado: F5, data, responsavel, escopo".

## 2. Ordem recomendada tratada como opcional demais

**Brecha:** a ordem F5 -> F2 -> F3 -> F4 -> F6 -> F1 -> F7 e apresentada como "recomendada", nao obrigatoria.

**Caminho de exploracao:** implementar F6 antes de F2, criando totalizadores baseados em `contrato` texto livre ou heuristica temporaria, gerando retrabalho e dados inconsistentes.

**Endurecimento:** separar "ordem obrigatoria por dependencia" de "ordem sugerida"; declarar que F6 nao pode comecar sem `contrato_id` persistido.

## 3. F8 e descrita como prerequisito logico, mas nao bloqueia F2 formalmente

**Brecha:** `PLAN.md` diz que F8 e prerequisito logico para F2, mas a ordem recomendada coloca F2 antes e o snapshot sugere F5 -> F2.

**Caminho de exploracao:** entregar selecao de contrato no frontend/backend, mas deixar o parser continuar inferindo contrato interativamente ou preenchendo `contrato` legado, violando a associacao real ao contrato selecionado.

**Endurecimento:** declarar checkpoint: "F2 so esta concluida quando uploads novos gravam `upload_batches.contrato_id` e linhas extraidas recebem contrato da sessao, sem menu interativo".

## 4. "Backend retorna 400, frontend faz redirect" deixa endpoints inconsistentes

**Brecha:** Decisao #9 define uma dependencia `require_contrato`, mas permite cria-la em `dependencies.py` ou `security.py` e diz "endpoints como" usam a dependencia.

**Caminho de exploracao:** proteger apenas `POST /api/uploads` e esquecer `GET /api/contratos/{id}/totais` ou endpoints futuros, criando telas que funcionam com contrato inexistente ou stale.

**Endurecimento:** listar todos os endpoints que exigem contrato e exigir teste para cada um: sem sessao, sem auth, contrato inexistente, contrato inativo.

## 5. Sem regra de autorizacao por usuario/contrato

**Brecha:** o plano exige login e selecao de contrato, mas nao define se todo usuario pode acessar todos os contratos.

**Caminho de exploracao:** implementar `GET /api/contratos` autenticado retornando toda a base e permitir qualquer usuario escolher qualquer contrato. Tecnicamente cumpre o plano, mas pode violar controle institucional.

**Endurecimento:** decidir explicitamente o modelo atual: "todos usuarios autenticados veem todos os contratos" ou criar tabela de permissoes. Se for aberto, registrar o risco.

## 6. Business key global conflita com contratos diferentes

**Brecha:** `business_key` nao muda e "uma mesma NF nao pode existir duas vezes mesmo em contratos diferentes".

**Caminho de exploracao:** se uma NF for legitimamente associada a contrato errado no primeiro upload, uma re-submissao correta em outro contrato sera deduplicada e bloqueada silenciosamente.

**Endurecimento:** definir processo de correcao de contrato para NF existente, com auditoria, ou revisar a chave para incluir `contrato_id` se a regra fiscal permitir.

## 7. Campos `nullable` para legado podem virar permissao permanente

**Brecha:** `contrato_id` e `upload_file_id` sao nullable para batches antigos, mas o plano tambem exige obrigatoriedade para novos.

**Caminho de exploracao:** deixar os campos nullable sem validacao aplicacional e continuar criando registros novos sem FK "para compatibilidade".

**Endurecimento:** adicionar constraints aplicacionais e testes: registros criados apos F2/F4 devem ter FK obrigatoria; nullable apenas para dados historicos.

## 8. Alembic automatico no `start.ps1` esta subespecificado

**Brecha:** Decisao #3 diz executar `alembic upgrade head` antes do Docker Compose, mas o banco Postgres so sobe pelo Compose.

**Caminho de exploracao:** implementar comando que falha quando o banco ainda nao esta ativo, ou rodar migration contra SQLite/local errado. O script "tem Alembic", mas nao migra o ambiente real.

**Endurecimento:** definir fluxo operacional exato: subir DB, aguardar healthcheck, rodar Alembic dentro do container/rede correta, depois iniciar backend.

## 9. Testes nao usam migrations

**Brecha:** testes continuam usando `create_all`, entao nao validam migrations.

**Caminho de exploracao:** quebrar uma migration de producao enquanto todos os testes passam, porque o schema final dos models esta correto.

**Endurecimento:** adicionar ao menos um teste/CI smoke de Alembic contra banco vazio: `alembic upgrade head`.

## 10. "Frontend verifica >550" pode substituir validacao real

**Brecha:** F5 pede validacao backend e frontend, mas implementador apressado pode tratar o frontend como suficiente.

**Caminho de exploracao:** desabilitar botao com 551 arquivos, mas aceitar request manual via API, consumindo recursos.

**Endurecimento:** declarar backend como fonte de verdade e teste obrigatorio antes de qualquer IO.

## 11. "Antes de qualquer IO" nao define o que conta como IO

**Brecha:** F5 pede contar arquivos antes de IO, mas frameworks podem materializar uploads temporarios antes do handler.

**Caminho de exploracao:** fazer validacao dentro do endpoint depois que todos os arquivos ja foram recebidos pelo servidor, cumprindo o texto no nivel do codigo mas nao protegendo rede/memoria.

**Endurecimento:** documentar limite de camada HTTP/proxy quando aplicavel e aceitar que F5 protege processamento, nao necessariamente upload bruto.

## 12. `nf_pending` bloqueia batch, mas nao define estado transacional

**Brecha:** F8 diz que Tipo 1 bloqueia o batch inteiro e linhas ja inseridas permanecem em abandono.

**Caminho de exploracao:** inserir parte do batch, criar pendencia, usuario abandona, e UI apresenta lote como parcialmente bem-sucedido sem status claro.

**Endurecimento:** definir estados de batch (`processando`, `pendente_usuario`, `concluido_parcial`, `abandonado`) e como cada um aparece na UI/API.

## 13. Retomar processamento apos resolver pendencia nao tem mecanismo

**Brecha:** `POST /pending/{id}/resolve` "backend retoma o processamento do batch", mas nao define fila, cursor, worker ou reentrada idempotente.

**Caminho de exploracao:** marcar pendencia como resolvida e exigir que o usuario reenvie arquivos restantes manualmente, alegando que a NF foi resolvida.

**Endurecimento:** especificar mecanismo: armazenar lista de arquivos restantes e indice atual, ou declarar que retomar significa reprocessar o batch idempotentemente.

## 14. Timeout de abandono "a definir" permite nunca abandonar

**Brecha:** F8 deixa timeout indefinido.

**Caminho de exploracao:** implementar sem job de abandono; pendencias ficam eternamente em `aguardando`, bloqueando relatórios e confundindo usuarios.

**Endurecimento:** definir valor inicial, por exemplo 24h, e job/rotina responsavel pela transicao.

## 15. Tipo 1 vs Tipo 2 depende de linhas fixas do parser

**Brecha:** a classificacao de erros referencia numeros de linha do `main.py`, mas o parser sera substituido periodicamente.

**Caminho de exploracao:** apos nova versao, as linhas mudam; erros de campo faltante caem como `erro_parsing`, sem modal, ou erros estruturais viram preenchimento manual inadequado.

**Endurecimento:** classificar por excecoes tipadas/codigos de erro, nao por posicao no arquivo.

## 16. "Nao apagar funcoes" pode congelar codigo perigoso

**Brecha:** regra de preservar parser de desenvolvimento proibe apagar funcoes/variaveis existentes.

**Caminho de exploracao:** manter chamadas interativas perigosas ou codigo morto importavel "para preservar", aumentando risco de execucao acidental.

**Endurecimento:** permitir isolamento seguro: codigo dev pode permanecer, mas deve ser inacessivel em modo web por guardas testados.

## 17. "Comentar chamadas que mudam" pode duplicar logica sem garantia

**Brecha:** exigir comentario da chamada antiga acima da nova aumenta ruído, mas nao garante comportamento equivalente.

**Caminho de exploracao:** deixar comentario correto e implementar substituto incompleto; revisão visual passa porque o ritual foi cumprido.

**Endurecimento:** exigir entrada em `docs/MAIN_PROD_CHANGES.md` com motivo, teste associado e comportamento antes/depois.

## 18. LLM cleaner "desativado em producao" sem guarda formal

**Brecha:** o cleaner esta comentado por performance, mas nao ha flag central que impeça reativacao acidental.

**Caminho de exploracao:** descomentar `batch_clean` em uma alteracao de parser e causar latencia de minutos ou chamadas externas inesperadas.

**Endurecimento:** controlar por env var explicita (`ENABLE_LLM_CLEANER=false`) e teste garantindo default desligado.

## 19. Chamadas externas do parser nao estao governadas

**Brecha:** `cnpj_lookup.py` pode chamar servico externo quando cache nao tem CNPJ; OpenRouter existe no cleaner.

**Caminho de exploracao:** rodar processamento em ambiente sem internet ou com dados sensiveis indo a API externa, mantendo o plano porque "sem key retorna gracioso".

**Endurecimento:** documentar politica de rede/dados e adicionar modo offline obrigatorio para producao institucional.

## 20. PDF sem magic bytes deferido cria janela de abuso

**Brecha:** Decisao #10 transfere validacao de PDF para versao futura do parser.

**Caminho de exploracao:** aceitar qualquer arquivo com extensao `.pdf`, gravar no storage e so falhar tarde no parser, consumindo armazenamento/processamento.

**Endurecimento:** mesmo deferindo validacao profunda, adicionar limite de tamanho, content type e rejeicao basica no upload.

## 21. F4 nao define controle de acesso ao PDF por lote/usuario

**Brecha:** endpoint de PDF exige autenticacao, mas nao define se usuario autenticado pode acessar qualquer `upload_file_id`.

**Caminho de exploracao:** usuario logado enumera UUIDs ou IDs vazados e baixa PDFs de outro contrato.

**Endurecimento:** validar autorizacao por contrato/lote e retornar 404 para arquivo fora do escopo permitido.

## 22. `Content-Disposition` com nome original pode permitir header injection

**Brecha:** F4 exige download com `original_filename` correto, sem regra de sanitizacao.

**Caminho de exploracao:** arquivo enviado com nome contendo caracteres de controle quebra header ou gera comportamento estranho no browser.

**Endurecimento:** sanitizar filename para header e manter nome original apenas como dado exibido escapado.

## 23. F1 tokens sem requisitos de entropia/reuso

**Brecha:** F1 diz "UUID seguro" e tokens de 128 chars no schema, mas nao define hashing em banco, uso unico, rotacao ou rate limit.

**Caminho de exploracao:** armazenar token em claro, permitir multiplos usos ate expirar, ou aceitar token antigo apos novo pedido.

**Endurecimento:** usar `secrets.token_urlsafe`, armazenar hash do token, limpar ao usar, invalidar tokens anteriores e limitar tentativas.

## 24. Login real sem protecao contra brute force

**Brecha:** F1 define hash e confirmacao, mas nao rate limit, lockout, captcha ou logging de tentativa.

**Caminho de exploracao:** endpoint cumpre criterios funcionais, mas permite ataque de senha online ilimitado.

**Endurecimento:** adicionar rate limiting por IP/e-mail e logs de auditoria para auth.

## 25. Usuario legado `user/password` pode vazar para producao por env mal definido

**Brecha:** manter usuario legado se `DEBUG=true`, mas nao define default seguro nem checagem de `APP_ENV`.

**Caminho de exploracao:** deploy com `DEBUG=true` por conveniencia e credencial fixa ativa em ambiente real.

**Endurecimento:** proibir legado quando `APP_ENV != development`; falhar startup se `DEBUG=true` em producao.

## 26. E-mail transacional "silenciosamente ignorado" conflita com F1

**Brecha:** F7 diz que sem `SMTP_HOST` envio e silenciosamente ignorado. F1 exige e-mail de confirmacao verificavel.

**Caminho de exploracao:** registrar usuario em ambiente sem SMTP, nunca enviar confirmacao, e ainda considerar endpoint implementado.

**Endurecimento:** separar modos: em dev pode logar link no console; em producao startup falha sem SMTP configurado.

## 27. F7 pede PDF original anexado em erro, mas nao limita tamanho

**Brecha:** erro de parser envia PDF ao admin com anexo, sem limite de tamanho nem politica de dados.

**Caminho de exploracao:** anexar PDFs grandes ou sensiveis, falhar SMTP ou expor documentos em caixas de e-mail.

**Endurecimento:** definir limite de anexo; acima do limite, enviar link autenticado com expiracao.

## 28. "SSE nunca bloqueia" nao define isolamento de falha

**Brecha:** F7 pede `asyncio.to_thread` ou `BackgroundTasks`, mas nao define timeout ou captura de excecao.

**Caminho de exploracao:** chamada SMTP fica presa em thread, acumula recursos e degrada uploads, embora nao bloqueie diretamente o stream.

**Endurecimento:** adicionar timeout, retry limitado e fila simples com logging estruturado.

## 29. Frontend monolitico "nao quebrar sem decisao explicita" pode impedir manutencao necessaria

**Brecha:** `frontend/AGENTS.md` protege a SPA monolitica, mas F1-F8 adicionam muitas telas e estados.

**Caminho de exploracao:** enfiar registro, reset, contratos, modais e totalizadores em `App.jsx`, cumprindo a regra e tornando o arquivo fragil.

**Endurecimento:** definir limiar: novas telas podem virar componentes locais em `frontend/src/components/` sem reestruturação arquitetural ampla.

## 30. Criterios de sucesso focam happy path e poucos negativos

**Brecha:** varias features listam checks funcionais, mas omitem concorrencia, idempotencia, autorizacao e rollback.

**Caminho de exploracao:** entregar endpoints que passam os criterios escritos, mas quebram com duplo clique, refresh, retry, sessao expirada ou duas abas.

**Endurecimento:** adicionar checklist transversal obrigatoria: auth, contrato ausente, id inexistente, retry/idempotencia, concorrencia minima e logs.

## 31. `base_contratos.json` como fonte de verdade sem validacao

**Brecha:** seed de contratos confia no JSON, mas nao define schema validation, normalizacao de CNPJ, moeda ou IDs estaveis.

**Caminho de exploracao:** gerar IDs novos a cada seed ou aceitar CNPJ invalido; uploads antigos passam a apontar para contratos inconsistentes.

**Endurecimento:** validar JSON antes do seed, derivar ID estavel de `numero` ou preservar ID existente, e testar idempotencia.

## 32. "ON CONFLICT(numero) DO UPDATE" pode sobrescrever historico silenciosamente

**Brecha:** seed atualiza contratos existentes com dados do JSON sem politica de auditoria.

**Caminho de exploracao:** alteracao acidental no JSON muda valores de contrato/CDE em producao, afetando totalizadores historicos.

**Endurecimento:** registrar diff de seed, exigir confirmacao para mudancas monetarias, ou versionar contratos.

## 33. Totalizadores nao definem status das NFs consideradas

**Brecha:** F6 soma `nf_entries.valor_total` filtrado por contrato, mas nao define se inclui abandonadas, duplicadas historicas, canceladas ou linhas pendentes resolvidas.

**Caminho de exploracao:** somar registros parciais/legados e exibir progresso financeiro enganoso.

**Endurecimento:** definir filtro exato: apenas entradas persistidas validas, contrato_id nao nulo, excluindo status cancelado se existir.

## 34. "Tela renderiza sem erros com base vazia" e fraco

**Brecha:** F3 aceita sucesso minimo visual sem definir estado vazio, paginacao ou ordenacao para ~140 contratos e crescimento futuro.

**Caminho de exploracao:** renderizar tabela gigante sem UX adequada, tecnicamente sem erro.

**Endurecimento:** definir estado vazio, ordenacao default, limite/paginacao ou virtualizacao quando necessario.

## 35. Documentos historicos podem ser usados para contradizer roadmap

**Brecha:** a hierarquia diz `docs/PLAN.md` e historico, mas ele ainda existe com plano do MVP e pode conter comandos/decisoes antigas.

**Caminho de exploracao:** citar `docs/PLAN.md` para justificar comportamento legado contra `planning/PLAN.md`.

**Endurecimento:** adicionar cabecalho em docs historicos: "Nao usar para escopo futuro; ver planning/PLAN.md".

## 36. Ortogonalidade de `BEHAVIORAL_GUIDELINES.md` gera conflito sem desempate

**Brecha:** diz que behavioral e "ortogonal - sempre se aplica", mas tambem que `PLAN.md > CLAUDE.md > demais`.

**Caminho de exploracao:** usar "se incerto, pare e pergunte" para bloquear tarefas claras do plano, ou usar "no features beyond asked" para nao implementar criterios implicitos de seguranca.

**Endurecimento:** declarar que guidelines governam processo, mas nao reduzem criterios de sucesso aprovados no plano.

## 37. "Se incerto, pergunte" pode virar fuga de responsabilidade

**Brecha:** `BEHAVIORAL_GUIDELINES.md` incentiva parar e perguntar quando confuso, sem diferenciar incerteza bloqueante de detalhe resolvivel por leitura.

**Caminho de exploracao:** interromper progresso por perguntas pequenas que o repositorio responde, mantendo postura "cautelosa".

**Endurecimento:** exigir que duvidas venham com contexto, opcoes e recomendacao, e que perguntas sejam reservadas a decisoes irreversiveis ou institucionais.

## 38. "Mudancas cirurgicas" pode impedir ajustes de contrato entre camadas

**Brecha:** guideline de tocar apenas o necessario pode ser explorada para alterar so backend ou so frontend em feature que exige ambos.

**Caminho de exploracao:** implementar endpoint sem UI ou UI sem validacao backend e alegar mudanca cirurgica.

**Endurecimento:** definir unidade minima por feature: backend, frontend, schema, tests e docs quando os criterios de sucesso cruzam camadas.

## 39. Falta definicao de ambiente alvo

**Brecha:** documentos alternam entre local, Hostinger semi-producao e servidor institucional futuro.

**Caminho de exploracao:** tomar decisoes de seguranca fracas dizendo que e local, ou complexas demais dizendo que mira institucional.

**Endurecimento:** declarar para cada feature o ambiente alvo do ciclo: local/dev, Hostinger semi-producao ou institucional futuro.

## 40. Sem criterio de pronto global

**Brecha:** cada feature tem criterios, mas nao ha Definition of Done transversal.

**Caminho de exploracao:** marcar feature concluida sem atualizar docs, sem migration, sem teste, sem build frontend, ou sem changelog do parser.

**Endurecimento:** adicionar DoD: testes relevantes passam, `npm run build` quando frontend muda, migration ou justificativa, docs atualizados, changelog do parser quando `main.py` muda.

