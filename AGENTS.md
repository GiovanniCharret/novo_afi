
## Business Requirements

Este projeto está construindo um sistema web com área logada para processamento e consulta de notas fiscais em PDF.

Principais funcionalidades:
- O usuário pode fazer login
- Quando autenticado, o usuário acessa uma área logada
- Na área logada, o usuário pode enviar um conjunto de PDFs compatíveis com o parser existente
- O backend deve processar os PDFs usando a lógica já consolidada do script atual
- O sistema deve exibir uma tabela baseada no output consolidado do parser
- As informações processadas devem persistir entre sessões
- O sistema não pode duplicar notas já processadas anteriormente independente da troca de usuário
- Se o usuário enviar novas notas em sessões futuras, apenas as novas devem ser adicionadas à base e exibidas na tabela
- O histórico do usuário autenticado deve sempre refletir o estado persistido, e não apenas a sessão atual

## Limitations

Para o MVP:
- Haverá autenticação simples, mas a modelagem deve suportar múltiplos usuários no banco
- O sistema rodará localmente ou em ambiente simples de desenvolvimento
- O parser existente em Python é a fonte de verdade para a extração dos dados dos PDFs
- O frontend não deve conter lógica de parsing de PDF
- O sistema deve aceitar apenas PDFs compatíveis com o fluxo de processamento atual
- O sistema não deve reprocessar ou duplicar notas já cadastradas independente de troca de usuário

## Technical Decisions

- O site pode ser construído em Node.js / JavaScript ou stack web equivalente
- O backend web deve integrar com o parser Python existente, preferencialmente reaproveitando sua lógica em vez de reescrevê-la
- A persistência deve ser feita em PostgreSQL
- A deduplicação deve ocorrer no backend e ser reforçada pelo banco
- A unicidade da nota deve ser baseada em chave de negócio derivada dos dados extraídos, como combinação de:
  - número da nota
  - CNPJ
  - data de emissão
  - valor
- O frontend deve consultar os dados persistidos no backend para montar a tabela exibida ao usuário
- O processamento deve suportar upload em lote
- O sistema deve registrar status por arquivo processado, como:
  - processado, duplicado, rejeitado, 
  erro de parsing

## Starting point

Já existe um script Python funcional que implementa a lógica principal de extração e consolidação de notas fiscais em PDF. A implementação web deve encapsular essa lógica e transformá-la em uma aplicação utilizável com autenticação, persistência e interface de consulta.

## Architectural rules

- Separar claramente frontend, backend web, parser e persistência
- O parser não deve depender da camada de interface
- O frontend apenas envia arquivos, consulta resultados e renderiza a tabela
- A lógica de deduplicação deve viver no backend
- A sessão do usuário não é fonte de verdade para os dados processados
- O banco de dados é a fonte de verdade
- O sistema deve preservar o comportamento do parser existente sempre que possível
- Preferir encapsular o parser atual como serviço ou adaptador interno

## Coding standards

1. Não sobre-engenheirar, Evitar excesso de programação defensiva e abstrações desnecessárias no MVP. 
2. Usar versões atuais e abordagem idiomática da stack escolhida
3. Em caso de bug, sempre identificar a causa raiz antes de corrigir
4. Não adicionar funcionalidades fora do escopo
5. Ser conciso com estrutura de código. Preferir funções pequenas e com responsabilidade clara. 
6. Reaproveitar ao máximo o parser existente



## Working documentation

Toda documentação de planejamento e execução deve ficar em `docs/`.
Revisar `docs/PLAN.md` antes de iniciar mudanças relevantes.