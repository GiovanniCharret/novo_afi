# Plano de Execucao

Este documento detalha a execucao do MVP descrito em `AGENTS.md`.
O objetivo e transformar o parser Python existente em uma aplicacao web com autenticacao simples, persistencia em PostgreSQL, upload em lote de PDFs e consulta persistida de notas fiscais processadas.

## Estado Atual

- Existe um parser Python legado em `backend/app/main_v9.py`.
- Existe um fallback OCR em `backend/app/ocr_reader.py`.
- O diretorio `frontend/` ainda esta vazio.
- O diretorio `backend/` ainda nao contem uma aplicacao web estruturada para o MVP.
- O diretorio `scripts/` existe, mas ainda nao contem automacao util para subir e parar a stack.

## Premissas de Execucao

- O parser existente sera reaproveitado e encapsulado, nao reescrito.
- O banco de dados sera a fonte de verdade para notas e historico exibido ao usuario.
- A deduplicacao sera feita no backend e reforcada por restricoes no banco.
- A autenticacao do MVP sera simples, mas a modelagem suportara multiplos usuarios.
- Cada parte abaixo deve ser concluida com verificacao objetiva antes de avancar.
- Quando uma etapa alterar arquitetura, contrato de dados ou modelagem, o usuario deve revisar e aprovar antes da execucao da etapa seguinte.

## Parte 1: Planejamento

Objetivo: preparar um plano executavel, documentar o estado atual e alinhar escopo antes de implementar.

### Subetapas

- [x] Revisar `AGENTS.md`, `docs/PLAN.md` e a estrutura real do repositorio.
- [x] Identificar o ponto de entrada do parser e o formato geral dos dados extraidos.
- [x] Registrar no plano as fases de execucao, dependencias e checkpoints de aprovacao.
- [x] Criar `frontend/AGENTS.md` descrevendo fielmente o codigo existente no frontend.
- [x] Corrigir problemas de encoding nos arquivos de documentacao tocados nesta fase.
- [x] Submeter o plano refinado para revisao e aprovacao do usuario.

### Testes

- Validar se `docs/PLAN.md` esta legivel em UTF-8.
- Validar se `frontend/AGENTS.md` corresponde ao estado atual do diretorio `frontend/`.
- Revisar manualmente se cada parte do projeto possui objetivo, checklist, testes e criterios de sucesso.

### Criterios de Sucesso

- O plano esta detalhado o bastante para orientar a execucao sem ambiguidades grosseiras.
- O usuario consegue aprovar ou pedir ajustes com base no documento.
- A documentacao refletiu o estado real do repositorio, sem antecipar implementacoes inexistentes.

## Parte 2: Scaffolding

Objetivo: criar a base minima da stack para desenvolvimento local com Docker, FastAPI e um fluxo simples de frontend estatico consumindo API.

### Subetapas

- [x] Definir a estrutura inicial de pastas para backend web, frontend buildado e scripts operacionais.
- [x] Criar configuracao Docker para aplicacao e PostgreSQL voltada ao desenvolvimento local.
- [x] Estruturar o backend FastAPI em `backend/` com app factory ou ponto de entrada claro.
- [x] Criar endpoint simples de healthcheck e um endpoint de exemplo para teste de integracao frontend-backend.
- [x] Criar pagina HTML estatica temporaria servida pelo backend em `/`.
- [x] Fazer a pagina chamar a API e renderizar uma resposta simples para validar o encanamento.
- [x] Criar scripts em `scripts/` para subir e parar a stack local.
- [x] Documentar como iniciar o ambiente.

### Testes

- Subir a stack localmente com os scripts.
- Acessar `/` e confirmar que a pagina e servida corretamente.
- Confirmar que a pagina consegue chamar a API de exemplo com sucesso.
- Confirmar que o backend responde healthcheck sem depender do frontend.

### Criterios de Sucesso

- Um fluxo "hello world" completo funciona localmente: browser -> frontend estatico -> API FastAPI.
- A infraestrutura minima para evoluir backend e frontend esta pronta.
- O processo de subir e parar o ambiente esta simples e repetivel.

## Parte 3: Adicionar o Frontend

Objetivo: substituir a pagina estatica temporaria por um frontend real, buildado estaticamente e preparado para o fluxo do produto.

### Subetapas

- [x] Escolher a stack de frontend mais adequada ao MVP e coerente com a manutencao futura.
- [x] Inicializar o frontend em `frontend/` com build de producao servivel pelo backend.
- [x] Definir a estrutura base de layout, estilos globais e organizacao de componentes.
- [x] Implementar tela principal com secao de upload preparada para um ou mais PDFs.
- [x] Implementar estrutura visual para tabela de notas persistidas.
- [x] Implementar estados vazios, carregamento e erro basicos.
- [x] Garantir responsividade minima para desktop e mobile.
- [x] Atualizar a documentacao do frontend, se a estrutura mudar de forma relevante.

### Testes

- Executar build do frontend com sucesso.
- Confirmar que o backend consegue servir os arquivos estaticos gerados.
- Validar renderizacao da pagina principal sem erros no console.
- Validar comportamento visual minimo em viewport desktop e mobile.

### Criterios de Sucesso

- O aplicativo exibe uma interface real e coerente com o fluxo final.
- O frontend esta pronto para conectar login, upload e tabela persistida.
- O build estatico do frontend esta integrado ao backend.

## Parte 4: Login Ficticio

Objetivo: adicionar uma experiencia simples de autenticacao para proteger a area logada no MVP.

### Subetapas

- [x] Definir abordagem de sessao simples no backend.
- [x] Criar endpoint de login com credenciais fixas `"user"` e `"password"`.
- [x] Criar endpoint de logout.
- [x] Proteger a rota principal ou a consulta inicial de dados para exigir autenticacao.
- [x] Implementar tela e formulario de login no frontend.
- [x] Implementar persistencia da sessao no cliente de forma simples e previsivel.
- [x] Implementar logout visivel na area autenticada.
- [x] Garantir que o frontend redirecione corretamente entre login e area logada.

### Testes

- Testar login com credenciais validas e invalidas.
- Testar acesso a rota protegida sem autenticacao.
- Testar logout e invalidez da sessao apos logout.
- Testar fluxo end-to-end basico: abrir app -> login -> acessar area -> logout.

### Criterios de Sucesso

- O usuario so acessa a area logada apos autenticacao.
- O logout remove o acesso imediatamente.
- A solucao e simples, mas nao impede a futura extensao para multiplos usuarios.

## Parte 5: Modelagem do Banco

Objetivo: definir e documentar a persistencia de notas, itens, uploads e vinculos necessarios ao MVP.

### Subetapas

- [ ] Inspecionar a estrutura de dados produzida pelo parser para identificar entidades persistentes.
- [ ] Propor schema inicial para usuarios, notas fiscais, itens da nota e historico de processamento por arquivo.
- [ ] Definir como representar a chave de negocio de deduplicacao.
- [ ] Definir restricoes unicas e indices necessarios.
- [ ] Definir relacionamento entre usuario autenticado e historico de uploads sem transformar a sessao em fonte de verdade.
- [ ] Documentar o modelo em `docs/`.
- [ ] Submeter a modelagem para aprovacao do usuario antes de implementar.

### Testes

- Revisao manual da aderencia do schema ao output do parser.
- Revisao manual da estrategia de deduplicacao contra os requisitos de negocio.
- Validacao logica de que o schema permite multiplos usuarios sem duplicar notas globais.

### Criterios de Sucesso

- O schema cobre persistencia das notas e dos itens extraidos.
- A deduplicacao por chave de negocio fica clara e aplicavel no banco.
- O usuario aprova a modelagem antes da implementacao.

## Parte 6: Backend

Objetivo: transformar o parser legado em uma capacidade reutilizavel do backend web, com persistencia e processamento em lote.

### Subetapas

- [ ] Isolar o parser em um adaptador interno com interface clara para o backend.
- [ ] Identificar e tratar dependencias do parser legado que impedem uso por requisicao.
- [ ] Implementar criacao automatica do banco e migrations iniciais ou estrategia equivalente para o MVP.
- [ ] Implementar endpoint para upload em lote de PDFs compativeis.
- [ ] Validar tipo de arquivo e rejeitar entradas fora do escopo do MVP.
- [ ] Processar cada arquivo individualmente, capturando status por arquivo.
- [ ] Persistir notas e itens alinhados ao retorno do parser.
- [ ] Aplicar deduplicacao no backend antes da insercao e reforcar no banco.
- [ ] Registrar status `processado`, `duplicado`, `rejeitado` e `erro de parsing`.
- [ ] Implementar endpoint de consulta das notas persistidas.
- [ ] Implementar endpoint de consulta do historico ou ultimo resultado de processamento, se necessario para o frontend.
- [ ] Cobrir o backend com testes unitarios e de integracao.

### Testes

- Testes unitarios do adaptador do parser com cenarios conhecidos.
- Testes de integracao dos endpoints de upload e listagem.
- Testes de deduplicacao reapresentando a mesma nota mais de uma vez.
- Testes de processamento em lote com mistura de sucesso, duplicado e erro.
- Testes de persistencia confirmando que dados permanecem entre sessoes.
- Testes de autenticacao nas rotas protegidas.

### Criterios de Sucesso

- O backend recebe PDFs, usa o parser existente e persiste apenas o que for novo.
- O banco e criado automaticamente no ambiente local quando necessario.
- O retorno da API distingue claramente o status de cada arquivo.
- A consulta de notas reflete o estado persistido, nao apenas a sessao atual.

## Parte 7: Integracao Frontend + Backend

Objetivo: conectar a interface final ao backend real para entregar o fluxo completo do produto.

### Subetapas

- [ ] Integrar o login do frontend com os endpoints reais do backend.
- [ ] Integrar o upload em lote com feedback por arquivo.
- [ ] Exibir no frontend os status de processamento retornados pela API.
- [ ] Consultar e renderizar a tabela persistida de notas fiscais processadas.
- [ ] Atualizar automaticamente a interface apos processamento bem-sucedido.
- [ ] Tratar estados de erro, duplicidade e lista vazia de forma clara.
- [ ] Refinar UX sem adicionar funcionalidades fora do escopo.
- [ ] Executar testes end-to-end e ajustes finais.

### Testes

- Teste end-to-end do fluxo completo: login -> upload -> processamento -> atualizacao da tabela.
- Teste de reenvio da mesma nota confirmando exibicao de duplicidade sem reinsercao.
- Teste de nova sessao confirmando que a tabela continua refletindo os dados persistidos.
- Teste de upload misto com PDFs validos e invalidos.
- Revisao manual da UX principal em ambiente local.

### Criterios de Sucesso

- O usuario autenticado consegue usar a aplicacao ponta a ponta.
- O frontend reflete o estado persistido do banco.
- O comportamento de deduplicacao e status por arquivo aparece corretamente na interface.

## Dependencias Entre Partes

- Parte 1 desbloqueia todas as demais.
- Parte 2 deve terminar antes da Parte 3 e da Parte 4.
- Parte 5 deve ser aprovada antes da implementacao completa da Parte 6.
- Parte 6 deve estar funcional antes da integracao real da Parte 7.

## Checkpoints de Aprovacao

- [x] Aprovar o plano refinado desta Parte 1.
- [ ] Aprovar a modelagem do banco na Parte 5 antes de implementar persistencia final.
- [ ] Confirmar readiness para a integracao final da Parte 7 se houver mudanca relevante de escopo.
