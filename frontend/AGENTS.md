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

- uma tela de login para o MVP
- uma area logada servida pelo backend em `/`
- upload em lote conectado ao backend real
- exibicao de status por arquivo retornado pela API
- tabela persistida carregada de `nf_entries`
- atualizacao automatica da tabela apos upload bem-sucedido
- estados basicos de carregamento, vazio e erro

## Limitacoes Atuais

- O parser legado continua encapsulado no backend e ainda depende de validacao com PDFs reais do fluxo final.
- A autenticacao atual usa credenciais ficticias fixas.

## Proximas Atualizacoes Esperadas

Este arquivo deve ser atualizado quando houver:

- autenticacao
- organizacao maior de componentes
- refinamento visual do fluxo de upload e tabela
- testes de frontend
