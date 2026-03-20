# Frontend Notes

## Stack Atual

O frontend agora usa:

- React 19
- Vite 7
- JavaScript

## Estrutura

- `src/main.jsx`: ponto de entrada do frontend.
- `src/App.jsx`: composicao principal da tela inicial do MVP.
- `src/styles.css`: estilos globais e layout da aplicacao.
- `vite.config.js`: configuracao de build estatico.
- `package.json`: scripts e dependencias do frontend.

## Objetivo desta Fase

Nesta etapa, o frontend entrega:

- uma landing page real servida pelo backend em `/`
- estrutura visual pronta para upload de PDFs
- estrutura visual pronta para tabela persistida
- estados basicos de carregamento e vazio
- integracao simples com a API atual para confirmar comunicacao com o backend

## Limitacoes Atuais

- Ainda nao ha login real nesta fase.
- Ainda nao ha upload real para o backend.
- Ainda nao ha consulta persistida de notas fiscais.
- O parser legado ainda nao esta integrado a interface.

## Proximas Atualizacoes Esperadas

Este arquivo deve ser atualizado quando houver:

- autenticacao
- organizacao maior de componentes
- integracao real com a API de notas
- testes de frontend
