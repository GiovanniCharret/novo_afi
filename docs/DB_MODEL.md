# Modelagem do Banco

Este documento descreve a modelagem do PostgreSQL.

**Status**: o schema do MVP (Partes 1–7 de `docs/PLAN.md`) está em produção. As mudanças planejadas para o próximo ciclo (F1–F8 de `planning/PLAN.md`) estão listadas em "Mudanças planejadas" abaixo. Ver `planning/PLAN.md` → "Mudanças Transversais de Schema" para os DDLs canônicos das próximas migrations.

## Direcao Adotada

Por decisao de produto para o MVP, a modelagem foi simplificada para favorecer:

- leitura direta no banco
- menor complexidade de implementacao

Cada lancamento consolidado extraido pelo parser sera persistido como uma linha em uma unica tabela principal.

- a unicidade global continua protegida por uma chave de negocio no nivel da linha persistida

## Objetivos

- Persistir os lancamentos extraidos pelo parser existente.
- Persistir o historico de uploads e o status por arquivo processado.
- Suportar multiplos usuarios no banco desde o MVP.
- Impedir reinsercao da mesma nota ou lancamento, mesmo que enviado por outro usuario em outro momento.
- Permitir que o frontend consulte dados persistidos, nao apenas dados da sessao atual.

## Dados de Origem do Parser

O parser atual converge para uma estrutura tabular com estes campos:

- `descricao`
- `ncm`
- `quant`
- `preco_unitario`
- `numero_nf`
- `tipo_nota`
- `data_emissao`
- `cnpj`
- `fornecedor`
- `valor`
- `contrato`

Observacao importante:

- para notas de produto, uma mesma NF pode gerar varias linhas
- para notas de servico, o parser hoje gera uma unica linha representando o servico
- o parser tambem gera um log por arquivo com status como `processado`, `rejeitado` e erros

## Entidades Propostas

### 1. `users`

Responsabilidade:

- representar usuarios autenticados do sistema
- permitir evolucao futura para autenticacao menos ficticia

Campos sugeridos:

- `id` UUID PK
- `username` TEXT NOT NULL UNIQUE
- `password_hash` TEXT NOT NULL
- `display_name` TEXT NULL
- `created_at` TIMESTAMPTZ NOT NULL DEFAULT now()
- `updated_at` TIMESTAMPTZ NOT NULL DEFAULT now()

Observacoes:

- no MVP com credenciais fixas, ainda vale manter a tabela para suportar a modelagem multiusuario
- a sessao autenticada referencia um usuario, mas os dados persistidos continuam independentes da sessao

### 2. `upload_batches`

Responsabilidade:

- representar um envio em lote feito por um usuario autenticado
- agrupar varios arquivos enviados na mesma acao

Campos sugeridos:

- `id` UUID PK
- `user_id` UUID NOT NULL FK -> `users.id`
- `created_at` TIMESTAMPTZ NOT NULL DEFAULT now()

Observacoes:

- um lote existe mesmo se todos os arquivos falharem ou forem duplicados
- o frontend pode usar esta entidade depois para mostrar o resultado do envio atual

### 3. `nf_entries`

Responsabilidade:

- persistir cada linha consolidada produzida pelo parser
- servir como tabela principal consultada pelo frontend
- concentrar a deduplicacao global do que foi processado

Campos sugeridos:

- `id` UUID PK
- `business_key` TEXT NOT NULL UNIQUE
- `numero_nf` TEXT NOT NULL
- `cnpj` TEXT NOT NULL
- `data_emissao` DATE NOT NULL
- `tipo_nota` TEXT NOT NULL
- `fornecedor` TEXT NULL
- `descricao` TEXT NOT NULL
- `ncm` TEXT NULL
- `quantidade` NUMERIC(18, 4) NULL
- `preco_unitario` NUMERIC(18, 4) NULL
- `valor_total` NUMERIC(18, 2) NOT NULL
- `contrato` TEXT NULL
- `raw_payload` JSONB NOT NULL
- `created_at` TIMESTAMPTZ NOT NULL DEFAULT now()
- `updated_at` TIMESTAMPTZ NOT NULL DEFAULT now()

Observacoes:

- esta tabela representa diretamente o layout consolidado que hoje vai para a planilha final
- `raw_payload` guarda a linha original normalizada para auditoria e comparacao futura
- o `id` garante identidade tecnica da linha
- a `business_key` garante que a mesma linha nao seja reinserida

### 4. `upload_files`

Responsabilidade:

- registrar o resultado individual de cada arquivo recebido no upload
- preservar historico de sucesso, duplicidade, rejeicao e erro

Campos sugeridos:

- `id` UUID PK
- `upload_batch_id` UUID NOT NULL FK -> `upload_batches.id`
- `original_filename` TEXT NOT NULL
- `file_sha256` TEXT NULL
- `status` TEXT NOT NULL
- `status_reason` TEXT NULL
- `parser_error` TEXT NULL
- `inserted_count` INTEGER NOT NULL DEFAULT 0
- `duplicate_count` INTEGER NOT NULL DEFAULT 0
- `created_at` TIMESTAMPTZ NOT NULL DEFAULT now()

Valores esperados para `status`:

- `processado`
- `duplicado`
- `rejeitado`
- `erro_parsing`

Observacoes:

- um unico arquivo pode gerar varias linhas consolidadas
- por isso, no MVP, `upload_files` guarda o resumo do resultado do arquivo em vez de apontar para apenas uma linha
- `file_sha256` e util para rastreabilidade e diagnostico, mas a deduplicacao principal nao deve depender apenas dele

## Estrategia de Deduplicacao

## Regra Principal

Como o parser atual produz uma tabela consolidada, a deduplicacao do MVP vai ocorrer no nivel da linha persistida.

A `business_key` deve ser derivada de:

- `numero_nf`
- `cnpj`
- `data_emissao`
- `valor_total`
- `descricao`

Se ficar necessario maior discriminacao depois, `ncm` e `contrato` podem ser adicionados sem quebrar a ideia central.

## Forma Recomendada

Gerar a `business_key` no backend a partir dos dados ja normalizados:

- `numero_nf`: trim, sem mascaras desnecessarias
- `cnpj`: somente digitos
- `data_emissao`: formato ISO `YYYY-MM-DD`
- `valor_total`: formato decimal canonico com 2 casas
- `descricao`: trim com normalizacao basica de espacos

Exemplo conceitual:

```text
12345|25086034000171|2025-03-10|1500.00|SERVICO DE MANUTENCAO PREVENTIVA
```

Opcionalmente, o backend pode armazenar um hash dessa string, mas para o MVP um campo textual unico ja resolve bem e e facil de debugar.

## Papel do Banco

O banco reforca a deduplicacao com:

- UNIQUE em `nf_entries.business_key`

Assim, mesmo se houver falha de concorrencia no backend, a duplicacao continua bloqueada.

## Historico por Usuario Sem Transformar Sessao em Fonte de Verdade

Para cumprir os requisitos, o historico do usuario precisa refletir o estado persistido sem depender da sessao.

Abordagem proposta:

- a linha consolidada existe uma vez em `nf_entries`
- cada envio gera um `upload_batch`
- cada arquivo do lote gera um `upload_files`
- o arquivo pode apontar para uma linha nova ou ja existente

Isso permite dois usos no frontend:

1. listar o resultado do ultimo upload do usuario autenticado via `upload_batches` e `upload_files`
2. listar a tabela persistida principal a partir de `nf_entries`

Observacao de negocio:

- como o requisito afirma que a nota nao deve duplicar independentemente da troca de usuario, a tabela principal deve ser global
- o usuario se relaciona com o evento de upload, nao com a propriedade exclusiva da nota

## Schema Relacional Resumido

```text
users 1---N upload_batches 1---N upload_files N---1 nf_entries
```

Interpretacao:

- um usuario faz varios lotes
- um lote contem varios arquivos
- um arquivo pode resultar em uma linha consolidada persistida

## Tipos e Normalizacao

Recomendacoes para a implementacao:

- datas persistidas como `DATE` ou `TIMESTAMPTZ` conforme o campo
- valores monetarios como `NUMERIC`, nao `FLOAT`
- CNPJ persistido ja normalizado em digitos
- numeros e quantidades convertidos do formato brasileiro para decimal canonico no backend

## Campos Minimos Expostos ao Frontend

Para a tabela principal:

- `id`
- `numero_nf`
- `cnpj`
- `data_emissao`
- `tipo_nota`
- `fornecedor`
- `descricao`
- `ncm`
- `quantidade`
- `preco_unitario`
- `valor_total`
- `contrato`

Para o resultado do upload:

- `original_filename`
- `status`
- `status_reason`
- `parser_error`
- `inserted_count`
- `duplicate_count`

## Decisoes Deliberadamente Adiadas

Estas decisoes nao sao necessarias para aprovar a modelagem do MVP:

- armazenamento binario do PDF no banco ou fora dele
- versionamento de parser por linha processada
- trilha de auditoria completa de alteracoes manuais
- autorizacao avancada por perfis

## Proposta de DDL Inicial

```sql
create table users (
  id uuid primary key,
  username text not null unique,
  password_hash text not null,
  display_name text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table upload_batches (
  id uuid primary key,
  user_id uuid not null references users(id),
  created_at timestamptz not null default now()
);

create table nf_entries (
  id uuid primary key,
  business_key text not null unique,
  numero_nf text not null,
  cnpj text not null,
  data_emissao date not null,
  tipo_nota text not null,
  fornecedor text,
  descricao text not null,
  ncm text,
  quantidade numeric(18, 4),
  preco_unitario numeric(18, 4),
  valor_total numeric(18, 2) not null,
  contrato text,
  raw_payload jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table upload_files (
  id uuid primary key,
  upload_batch_id uuid not null references upload_batches(id) on delete cascade,
  original_filename text not null,
  file_sha256 text,
  status text not null,
  status_reason text,
  parser_error text,
  inserted_count integer not null default 0,
  duplicate_count integer not null default 0,
  created_at timestamptz not null default now()
);
```

## Recomendacao

A recomendacao e aprovar esta modelagem simplificada como base da Parte 6, com tres compromissos de implementacao:

- encapsular a normalizacao de `business_key` no backend antes do insert
- converter os campos numericos e de data do parser para tipos canonicos antes de persistir
- manter a tabela principal o mais parecida possivel com a planilha consolidada usada no fluxo atual

---

## Mudancas planejadas (proximo ciclo — F1 a F8)

Esta secao resume as mudancas de schema do roadmap em `planning/PLAN.md`. Os DDLs canonicos vivem la; aqui apenas o overview para nao duplicar fonte de verdade.

### Tabela `users` — F1 + Decisao #5

Colunas novas (todas necessarias para auth real):

- `email VARCHAR(255) UNIQUE NOT NULL` — identificador unico de login (substitui `username` no fluxo novo)
- `email_confirmed BOOLEAN NOT NULL DEFAULT FALSE`
- `confirmation_token VARCHAR(128)` + `token_expires_at TIMESTAMPTZ`
- `reset_token VARCHAR(128)` + `reset_expires_at TIMESTAMPTZ`

Coluna existente alterada:

- `username` passa a `nullable=True`. Mantida apenas por compat com seed legado (`DEBUG=true`); ninguem novo cadastra com username.

Hash de senha (Decisao #2): `passlib[bcrypt]` cost 10. `CryptContext` configurado com `schemes=["argon2", "bcrypt"]` para permitir migracao automatica para argon2id quando a instituicao definir o algoritmo institucional. Esqueleto em `backend/app/security.py`.

### Tabela `contratos` (nova) — F2

Seed a partir de `base_contratos.json` (~140 entradas). DDL completo em `planning/PLAN.md`.

Campos: `id, numero (UNIQUE), sigla, cnpj, tranche, uf, valor_contrato, valor_cde, participacao_cde, tipo_contrato (LPT|MLA), ativo, created_at`.

### Tabela `upload_batches` — F2 + F8

- `contrato_id VARCHAR(36) NOT NULL REFERENCES contratos(id)` (nullable em batches antigos via migration; obrigatorio em novos).
- `status VARCHAR(16)` — `processando` | `concluido` | `abandonado` (introduzido em F8 para suportar bloqueio/abandono de pendencias — Decisao #8).

### Tabela `nf_entries` — F2 + F4 + F8

Colunas novas:

- `contrato_id VARCHAR(36) REFERENCES contratos(id)` — complementa o `contrato` texto livre atual (este permanece como legado).
- `upload_file_id VARCHAR(36) REFERENCES upload_files(id)` — necessario para F4 (visualizar/baixar PDF a partir da linha).

**Mudanca critica em F8 (Decisao #8)**: as **11 colunas** que vem de `default_nf_template` (`descricao, ncm, quant, preco_unitario, numero_nf, tipo_nota, data_emissao, cnpj, fornecedor, valor, contrato`) viram `NOT NULL`. Linha com qualquer campo `""` ou `None` e considerada falha grave do parser e nao pode entrar no banco. Eventual backfill de linhas historicas com NULL pode ser necessario antes do `ALTER COLUMN ... SET NOT NULL`.

A `business_key` **nao muda** — uma mesma NF nao pode existir duas vezes mesmo em contratos diferentes.

### Tabela `nf_pending` (nova) — F8

NFs que o parser identificou mas nao conseguiu preencher 100% dos campos obrigatorios. Aguardam preenchimento manual via modal no frontend.

```sql
CREATE TABLE nf_pending (
    id                  VARCHAR(36) PRIMARY KEY,
    upload_file_id      VARCHAR(36) NOT NULL REFERENCES upload_files(id) ON DELETE CASCADE,
    upload_batch_id     VARCHAR(36) NOT NULL REFERENCES upload_batches(id) ON DELETE CASCADE,
    contrato_id         VARCHAR(36) NOT NULL REFERENCES contratos(id),
    prefilled_json      TEXT NOT NULL,
    missing_fields_json TEXT NOT NULL,
    status              VARCHAR(16) NOT NULL DEFAULT 'aguardando',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at         TIMESTAMPTZ
);
```

Status: `aguardando` | `resolvido` | `abandonado`. Indices em `status` e `upload_batch_id`.

### Tabela `upload_files` — F8

Status `aguardando_preenchimento` adicionado ao enum logico (linha tem 1+ NF em `nf_pending`). Sem schema change na coluna em si — o enum hoje e `VARCHAR`.

Coluna nova:

- `stored_filename VARCHAR(255)` — UUID ou nome real no disco. Permite migracao futura para object storage sem mudar a logica de identificar o arquivo (Decisao #4 de storage).

### Schema management — Decisao #3

Hoje: `init_db()` (`SQLAlchemy create_all`) no `lifespan`. Adicionar coluna em tabela existente nao funciona com `create_all`.

A partir de F1: **Alembic**, executado via `alembic upgrade head` no `start.ps1` antes de `docker compose up`. Primeira migration = baseline gerada via autogenerate contra schema atual. Migrations subsequentes uma por feature. Testes (`conftest.py`) continuam usando `init_db()` direto sobre os models — testes nao rodam migrations.
