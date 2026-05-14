# PENDING_DECISIONS.md

Decisões **explicitamente deferidas** para definição institucional futura. Não são decisões em aberto deste ciclo de desenvolvimento — todas elas têm um caminho temporário registrado em `planning/PLAN.md` que cobre a fase Hostinger (semi-produção). Quando o sistema migrar para o servidor institucional, cada item desta lista volta à mesa para revisão pelos superiores institucionais.

A diferença entre **decisão resolvida** (em `planning/PLAN.md` → "Decisões Pendentes") e **decisão deferida** (aqui): resolvida tem caminho definitivo no escopo atual; deferida tem caminho temporário e a definição final cabe a outro stakeholder.

---

## 1. Provedor SMTP institucional

- **Estado atual** (Decisão #1 resolvida em `planning/PLAN.md`): Hostinger SMTP (`smtp.hostinger.com:587` STARTTLS) com domínio Hostinger próprio. Volume estimado ≤10 e-mails/h.
- **A decidir pela instituição**: provedor SMTP final (servidor institucional próprio? Office 365 institucional? outro?). Domínio remetente (`@enbpar.gov.br` ou similar?). Política de retenção de e-mails transacionais.
- **Migração futura**: troca de variáveis `SMTP_*` em `.env` + reconfiguração de SPF + DKIM + DMARC no DNS institucional. Sem alteração de código.

## 2. Algoritmo de hash de senha institucional

- **Estado atual** (Decisão #2 resolvida em `planning/PLAN.md`): bcrypt cost 10 via `passlib[bcrypt]`. `CryptContext` configurado em modo multi-scheme (`schemes=["argon2", "bcrypt"]`, `default="bcrypt"`, `deprecated=["bcrypt"]`) para permitir migração automática para argon2id.
- **A decidir pela instituição**: existe norma de TI que exige algoritmo específico (argon2id? PBKDF2? outro)? Política mínima de senha (comprimento, expiração, complexidade)?
- **Migração futura**: trocar `default="bcrypt"` para `default="argon2"` em `backend/app/security.py` + adicionar `argon2-cffi` ao `requirements.txt`. Logins bem-sucedidos re-hasheiam silenciosamente — em ~1 ciclo de logins toda a base estará migrada sem reset de senha forçado.

## 3. Storage de PDFs (filesystem vs. object storage)

- **Estado atual** (Decisão #4 resolvida em `planning/PLAN.md`): filesystem local em `backend/banco_de_nf/<batch_id>/<stored_filename>`. F4 adiciona abstração `get_pdf_path(upload_file)` em `backend/app/storage.py` para isolar o ponto de leitura.
- **A decidir pela instituição**: o servidor institucional vai prover storage interno? Há exigência de criptografia at-rest? Há política de retenção (quanto tempo guardar PDFs)? Há exigência de imutabilidade (WORM) para auditoria fiscal?
- **Migração futura**: trocar a implementação de `get_pdf_path` (e a função de save no upload) para apontar para object storage S3-compatível. Schema já está preparado — `upload_files.stored_filename` é UUID que vira a key do bucket.

## 4. Política de backup operacional

- **Estado atual**: rsync semanal de `UPLOAD_STORAGE_DIR` para destino externo. **Não automatizado nesta fase** — registrado como TODO de ops em `planning/PLAN.md`.
- **A decidir pela instituição**: frequência (diária? semanal? em tempo real via réplica)? Destino (B2/S3? servidor institucional? fita?)? Política de retenção e teste de restore?
- **Migração futura**: depende do storage definitivo (item 3). Se filesystem permanece, rsync com agenda. Se object storage, replication policy nativa do bucket.

## 5. UX de múltiplos contratos por sessão

- **Estado atual** (Decisão #6 resolvida em `planning/PLAN.md`): `contrato_id` mora **apenas na sessão**, sem persistência em `users.ultimo_contrato_id`. Cada login novo recomeça do zero — usuário passa pela tela de seleção de contrato.
- **Contexto**: usuários reais trabalham em múltiplos contratos no mesmo dia, alternando.
- **A decidir pela instituição**:
  - Opção B: persistir `users.ultimo_contrato_id` e pré-selecionar (com confirmação) na tela de seleção. Reduz cliques mas mantém seguro.
  - Opção C: persistir e **pular a tela** quando há contrato salvo. Menor atrito, mas risco de upload no contrato errado.
  - Manter Opção A: tela sempre.
- **Migração futura**: mudança na coluna `users` + ajuste no frontend pós-login. Coluna nullable + lógica condicional. Reversível.


---

## Como esta lista é mantida

- Adicionar novo item somente quando uma decisão é deferida explicitamente para a instituição (não para "depois") — caso contrário, registrar em `planning/PLAN.md` → "Decisões Pendentes".
- Cada item deve ter: estado atual (com referência à decisão resolvida), o que falta decidir, e qual o caminho de migração.
- Quando a instituição decidir, mover a decisão resolvida para `planning/PLAN.md` (seção "Decisões Pendentes" com data e responsável) e remover o item daqui.
