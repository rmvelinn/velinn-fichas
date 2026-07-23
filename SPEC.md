# SPEC.md — VELINN Ficha Cadastral (`velinn-fichas`)

> **Documento retroativo.** Escrito em 2026-07-23 a partir de inspeção direta do
> código-fonte de um sistema já em produção — não é uma especificação
> prévia ao desenvolvimento. Segue o template de `FRAMEWORK_PROJETOS_CLAUDE_CODE.md`
> seção 1.1, adaptado para documentar o que já existe antes de qualquer
> desenvolvimento novo começar.

---

## 1. Visão geral e objetivos

**O que o projeto resolve:** substitui o processo manual de coleta de dados
cadastrais de novos parceiros (pousadas/hotéis) da rede VELINN — antes feito
por planilha ou formulário genérico — por um fluxo digital ponta a ponta:
geração de link único → preenchimento pelo parceiro → geração automática de
PDF + consulta de CNPJ/QSA → upload no Drive da pousada → notificação por
e-mail ao parceiro e ao time interno.

**Por que construir e não comprar:** o processo está amarrado à estrutura de
pastas do Google Drive por pousada, ao painel interno de permissões (`velinn-hub`)
e ao fluxo de aprovação/gerente responsável específicos da VELINN — nenhuma
ferramenta de formulário genérica (Typeform, Google Forms) cobre a geração de
PDF com layout próprio + integração Drive por pasta + BrasilAPI + Gmail com
domain-wide delegation na mesma peça.

**Escopo do sistema:** dois apps que compartilham banco (Supabase) e um
segredo de comunicação interno:
- `velinn-fichas` — formulário público voltado ao parceiro (sem autenticação de
  usuário; o token do link é a credencial)
- módulo "fichas" dentro de `velinn-hub` — painel interno onde o gerente gera o
  link, acompanha status, edita, e vê log de alterações

---

## 2. Stack tecnológica

| Camada | Tecnologia |
|--------|-----------|
| Backend velinn-fichas | Python 3 + FastAPI + Uvicorn |
| Backend velinn-hub (módulo fichas) | Python 3 + FastAPI + Uvicorn |
| Banco de dados | Supabase (PostgreSQL) via REST API — Secret API Key `sb_secret_...` |
| Armazenamento de arquivos | Google Drive (Shared Drive) via Service Account, `supportsAllDrives=True` |
| E-mail | Gmail API via Service Account com domain-wide delegation |
| Geração de PDF | ReportLab (layouts: Ficha, Cartão CNPJ, QSA) |
| Consulta CNPJ | BrasilAPI pública (`brasilapi.com.br/api/cnpj/v1/{cnpj}`) — sem chave |
| Consulta CEP | ViaCEP pública (`viacep.com.br`) — sem chave |
| Frontend | HTML/CSS/JS puro — sem framework, zero dependências externas |
| Hospedagem | Render (free tier) |
| Repositórios | `rmvelinn/velinn-fichas` + `rmvelinn/velinn-hub` (GitHub, privados) |

**Decisão registrada — por que dois apps separados:** ver seção 6.1.

---

## 3. Estrutura de pastas

> Confirmada por auditoria do Claude Code em 2026-07-23 (ver seção 10).
> Ambos os apps são **monolíticos** — sem `models/`/`services/` separados,
> ao contrário do que a primeira versão retroativa deste documento supunha.

```
velinn-fichas/
├── api/
│   └── main.py                 # FastAPI app monolítico: rotas, PDF, Drive,
│                                # e-mail, CNPJ/CEP — tudo neste arquivo
├── cadastro.html                # form multi-step (raiz do projeto, não em static/)
├── render.yaml
├── requirements.txt
└── .env                          # não versionado

velinn-hub/ (módulo fichas)
├── hub/
│   └── api/
│       └── main.py             # monolítico: geração de link, listagem,
│                                # edição, log, permissões — tudo neste arquivo
└── ...                          # restante do hub (usuários, sessões, outros módulos)
```

---

## 4. Modelagem de dados essencial

### 4.1 Tabela principal: `fichas_cadastrais` (Supabase/PostgreSQL)

```sql
id                      uuid        PK
token                   text        UNIQUE — credencial do parceiro (link)
gerente_id / _nome / _email  text   — gerente responsável
nome_pousada            text
nome_proprietario       text
email_proprietario      text        -- recebe e-mail de agradecimento
drive_folder_id         text        -- pasta Drive selecionada no hub
status                  text        -- pendente | preenchido

-- Dados da empresa
razao_social, nome_fantasia, cnpj, endereco, numero, complemento,
bairro, cidade, estado, cep, email_administrativo

-- Dados do sócio
socio_nome, socio_data_nascimento, socio_cpf, socio_rg, socio_email,
socio_celular, socio_endereco, socio_numero, socio_complemento,
socio_bairro, socio_cep, socio_cidade, socio_estado

-- Testemunhas (v2 — array JSONB)
num_testemunhas         integer     DEFAULT 1
testemunhas             jsonb       DEFAULT '[]'
-- colunas legado v1 (mantidas por compatibilidade, não usar em código novo):
-- testemunha_nome/cpf/rg/email/data_nascimento

-- Resultado
pdf_drive_url           text
versao                  integer     DEFAULT 1

-- Rastreamento
visualizado_em          timestamptz -- 1ª abertura do link
criado_em               timestamptz
preenchido_em           timestamptz
```

### 4.2 Tabela `logs` (Supabase, compartilhada com o hub)

Registra histórico de edições da ficha (usada pelo modal "Ver Log" no hub).
**Pendência:** schema completo de `logs` (e das demais tabelas do hub —
`usuarios`, `sessoes`, `quadros`) ainda não documentado em `supabase_hub.sql`
— ver seção 8, item de baixa prioridade.

### 4.3 Estrutura de pastas no Google Drive (por pousada)

```
📁 Pasta da Pousada  ← selecionada pelo gerente no hub
└── 📁 Documentos
    ├── 📁 Documentos Hotel
    │   ├── Ficha Cadastral {NomePousada}.pdf
    │   ├── CARTÃO CNPJ.pdf
    │   └── QSA.pdf
    └── 📁 Documentos Velinn
        └── [futuro] Contrato Parceria +Proposta Velinn & {NomePousada}.docx
```

---

## 5. Especificação módulo a módulo (estado atual)

### 5.1 Geração de link (velinn-hub)
Gerente seleciona a pasta Drive da pousada e o número de testemunhas (0–5);
sistema gera `token` único e monta a URL pública para envio ao parceiro por
e-mail.

### 5.2 Formulário público (velinn-fichas)
Form multi-step: dados da empresa → dados do sócio (com autocomplete de CEP
via ViaCEP e máscara de data DD/MM/AAAA) → testemunhas (0–5, campos
dinâmicos). Marca `visualizado_em` na 1ª abertura do link. Proteção contra
double-submit: flag no frontend **e** `WHERE status=eq.pendente` no PATCH do
backend (defesa em profundidade contra race condition mobile).

### 5.3 Pós-submissão (síncrono)
Ao submeter, em sequência síncrona (sem background tasks — decisão registrada,
ver 6.3):
1. Gera PDF da ficha (ReportLab)
2. Consulta BrasilAPI (cartão CNPJ + QSA) e gera PDFs adicionais
3. Upload dos 3 PDFs no Drive (`supportsAllDrives=True`), na subpasta
   `Documentos/Documentos Hotel/`
4. E-mail de agradecimento ao parceiro (sócio + e-mail administrativo,
   deduplicado case-insensitive)
5. E-mail de notificação ao time interno (`NOTIF_EMAILS` + gerente responsável)

### 5.4 Painel interno (velinn-hub)
Lista fichas com status; botões de ação (ver PDF, editar, ver log, deletar)
condicionados a permissões granulares por usuário no array `agentes`:
`fichas_link`, `fichas_pdf`, `fichas_cnpj`, `fichas_editar`, `fichas_log`,
`fichas_deletar`. Admins também aparecem no dropdown de gerente responsável.
Edição via modal gera nova versão (`versao++`, novo arquivo PDF `_V2`, `_V3`...)
e grava entrada na tabela `logs`.

---

## 6. Decisões registradas

### 6.1 Decisão registrada — dois apps separados (hub + fichas)
**Confirmado:** `velinn-fichas` (público) e `velinn-hub` (interno) são
aplicações separadas, comunicando-se via header `X-Notif-Secret` (variável
`FICHAS_NOTIF_SECRET`), sem JWT entre elas.
**Implicações:** isola o formulário público do painel interno, URL limpa para
o parceiro, deploy independente de cada app. Qualquer mudança de contrato entre
os dois (ex: novo campo, novo endpoint interno) precisa ser sincronizada nos
dois repositórios manualmente — não há schema compartilhado versionado.

### 6.2 Decisão registrada — token como credencial única
**Confirmado:** o parceiro não tem autenticação de usuário; o `token` de 32
caracteres na URL é a única credencial.
**Implicações:** simplicidade máxima para o parceiro (não precisa criar conta),
mas qualquer pessoa com o link tem acesso de preenchimento — aceitável dado o
caso de uso (link enviado 1:1 por e-mail pelo gerente, não link público
divulgado).

### 6.3 Decisão registrada — pós-submissão síncrono, sem background tasks
**Confirmado:** toda a cadeia PDF → BrasilAPI → Drive → e-mails roda
sincronamente na mesma requisição HTTP do submit.
**Motivo:** Render free tier mata processos em background quando a requisição
HTTP original termina — background tasks (ex: `BackgroundTasks` do FastAPI)
não seriam confiáveis nesse ambiente.
**Trade-off aceito:** resposta ao parceiro demora ~5–10s. Implicação para o
futuro: se migrar de hospedagem (ver 6.7 / seção 8), reavaliar se background
tasks reais passam a ser viáveis e preferíveis para reduzir a espera do
parceiro.

### 6.4 Decisão registrada — RLS desabilitado no Supabase
**Confirmado:** Row Level Security desabilitado nas tabelas deste projeto.
**Motivo:** acesso ao Supabase é exclusivo via Secret API Key do backend
(`sb_secret_...`); não há acesso direto do frontend ao banco.
**Implicação:** qualquer novo cliente que precise falar direto com o Supabase
(ex: um frontend novo sem passar pelo backend) quebraria essa premissa de
segurança — deve passar pelo backend, não pelo banco direto.

### 6.5 Decisão registrada — migração para Supabase Secret API Key
**Confirmado em 2026-07-21:** migração do JWT legado `service_role` para a
nova Secret API Key (`sb_secret_...`), sem mudança de código — apenas troca de
variável de ambiente no Render.
**Implicação:** documentar essa data como marco de rotação de credencial, caso
seja necessário auditar quando o JWT antigo deixou de ser válido.

### 6.6 Decisão registrada — PDF sem sobrescrita (versionamento)
**Confirmado:** cada edição de ficha já preenchida incrementa `versao` e gera
um novo arquivo PDF (`_V2`, `_V3`...) em vez de sobrescrever o anterior.
**Motivo:** rastreabilidade — em caso de disputa ou erro de preenchimento,
todas as versões ficam preservadas no Drive.

### 6.7 Decisão registrada — cold start aceito temporariamente
**Confirmado:** hospedagem atual é Render free tier, com cold start de ~50s
após ~15 minutos sem tráfego, afetando o parceiro na abertura do link.
**Status:** aceito temporariamente; decisão de migrar (Render paid ou Railway)
está pendente — ver seção 8, prioridade alta. Não tratar como bug a resolver
por Claude Code sem essa decisão de negócio antes.

---

### 6.8 Decisão registrada — permissão admin por botão é intencional
**Confirmado em 2026-07-23:** a assimetria encontrada na auditoria (admin tem
acesso automático à **área** de fichas via `_tem_acesso_fichas`, mas precisa
de permissão explícita no array `agentes` para ações específicas como
deletar/ver log via `_tem_perm`) é **intencional, não lacuna**.
**Motivo:** nem todo admin deve poder deletar uma ficha — deletar exige uma
permissão adicional, específica, além de ser admin.
**Implicações:** nenhuma mudança de código necessária. Este item sai da lista
de pendências da auditoria.

---

## 7. Lista de endpoints/interfaces de referência

> Confirmada por auditoria do Claude Code em 2026-07-23 (ver seção 10).

**velinn-fichas (público):**
- `GET /cadastro/{token}` — carrega o formulário para o parceiro (`api/main.py:524`)
- `POST /api/cadastro/{token}/submeter` — submete os dados, dispara a cadeia
  PDF/Drive/e-mail (`api/main.py:548`)
- `POST /api/interno/cnpj` — consulta CNPJ, corpo JSON `{cnpj, folder_id}`,
  chamada pelo hub via header `X-Notif-Secret` (`api/main.py:489`)
- `GET /api/fichas/notif-emails` (chamada pelo fichas ao hub, com
  `X-Notif-Secret`)

**velinn-hub (módulo fichas, interno):**
- `POST /api/fichas/gerar` — cria registro + token, retorna URL (`hub/api/main.py:1010`)
- `GET /api/fichas` — lista fichas com status (filtrado por permissão)
- `GET /api/fichas/lista-simples` — listagem simplificada
- `GET /api/fichas/gerentes` — lista de gerentes para o dropdown
- `PATCH /fichas/{token}/editar` — edição (gera nova versão, path usa `token`, não `id`)
- `GET /fichas/{token}/log` — histórico de edições
- `DELETE /api/fichas/{token}` — exclusão
- `POST /api/fichas/{token}/cnpj` — dispara consulta de CNPJ para uma ficha específica

---

## 8. Roadmap faseado

> **Fases 0–N (já concluídas — sistema em produção hoje):** form multi-step,
> geração de PDF/CNPJ/QSA, upload Drive, e-mails, permissões granulares,
> versionamento com log. Não há necessidade de refazer roadmap retroativo
> fase a fase para o que já está funcionando — o que importa daqui pra frente
> é o que vem a seguir.

**Fases decididas após auditoria de 2026-07-23 (ver seção 10):**

| Fase | Entregável | Status |
|------|-----------|--------|
| 1 | Correção isolada em `velinn-fichas`: `db_get` inexistente, double-submit não bloqueado de fato, precedência de operador no set de destinatários, timestamps UTC nos PDFs de CNPJ/QSA, XSS em e-mail via f-string, log silencioso de erro de banco, import morto de `BackgroundTasks`, ajustes em `render.yaml`, timeout no fetch do frontend | ✅ Concluída e aprovada em 2026-07-23 (commit `63c5d27`, push feito). Validado manualmente em produção: double-submit bloqueado (mensagem amigável, sem 500), sem duplicação de PDF/e-mail, timestamp BRT correto nos PDFs de CNPJ/QSA. **Item de escape HTML (XSS) não testado manualmente com payload malicioso** — risco aceito como baixo (só afeta e-mail interno) |
| 1B | Correção isolada em `velinn-hub`: `BackgroundTask` do e-mail de link para o parceiro (hub confirmado em Render free tier — mesmo risco de silenciosamente nunca enviar), código morto (`_tem_acesso_fichas_raw`), log de criação de ficha invisível no modal "Ver Log" | ✅ Concluída e aprovada em 2026-07-23 (commit `7c03717`, push feito). Validado manualmente em produção: e-mail de link chega mesmo em envio síncrono, evento `gerar_ficha` aparece corretamente no modal "Ver Log". Item 3B (log de `deletar_ficha`) confirmado via query direta no Supabase — registro pós-deploy já no formato `token=XXXXXXXX`, registros anteriores à correção confirmam o bug antigo (token cru, sem prefixo) |

**Fases futuras (ainda em stand-by — aguardando decisão de negócio, sem
prioridade imediata):**

| Fase | Entregável | Status |
|------|-----------|--------|
| A | Resolver cold start — decidir Render paid ($7/mês) vs. Railway | ⏳ Standby — decisão de negócio pendente |
| B | Contrato V2.0 (DOCX pré-preenchido a partir de template Word, salvo em `Documentos/Documentos Velinn/`) | ⏳ Standby — depende de template Word ainda não entregue |
| C | Integração ClickUp (link gerado → status "Ficha Enviada"; preenchido → "Ficha Preenchida" + task de contrato) | ⏳ Standby — depende de plataforma ClickUp estar pronta; dados necessários: API Key, List ID, nomes exatos dos status |
| D | Retry em falhas de Drive/e-mail (hoje: falha silenciosa, parceiro recebe "sucesso" mesmo se upload/envio falhar) | ⏳ Standby — sem prioridade definida ainda, mas é dívida técnica de risco médio |
| E | Migração de infra (VPS próprio, `wikivelinn.com.br`, subdomínios `fichas.`/`hub.`, SSO via cookie compartilhado) | ⏳ Standby — planejada para depois da migração do WikiVelinn |
| F | `supabase_hub.sql` — documentar schema das tabelas do hub (`usuarios`, `logs`, `sessoes`, `quadros`) | ⏳ Baixa prioridade |
| G | Otimizar `_drive_upload` (recria cliente Drive 3–4× por submissão) | ⏳ Baixa prioridade — performance, não bug |
| H | Fase H — PDF da Ficha (principal) vai para a pasta raiz da pousada desde a primeira submissão (nunca esteve em `Documentos/Documentos Hotel/`, diferente de CNPJ/QSA que sempre foram salvos lá corretamente). Aguardando confirmação com a diretoria: manter a raiz como padrão oficial (e corrigir o SPEC.md, não o código) ou migrar para dentro da subpasta (código + reorganização do histórico no Drive) | ⏳ Aguardando resposta da diretoria (consultada em 2026-07-23) |

**Regra do framework aplicável:** nenhuma dessas fases entra em execução sem
você abrir explicitamente com "Vamos executar a Fase [X]" e o plano ser
apresentado antes de codar — mesmo sendo um roadmap retroativo, a disciplina
de fases vale a partir de agora para frente.

---

## 9. Dívida técnica conhecida (não é roadmap, é risco aceito e registrado)

| Item | Severidade | Observação |
|------|-----------|-----------|
| Sem retry em falhas de Drive/e-mail | Média | Ver Fase D |
| Foto de perfil pessoal do CRO aparece no Gmail do parceiro (`no-reply@velinn.com` usa alias pessoal) | Baixa | Logo já gerado (`velinn_profile.png`), falta aplicar na conta |
| Testemunhas no modal de edição não validadas em produção com fichas reais com testemunhas | Baixa | Pendente validação |
| `supabase_hub.sql` não existe | Baixa | Ver Fase F |

---

## 10. Auditoria de 2026-07-23

Primeira auditoria completa do sistema (investigação, sem correções),
conduzida pelo Claude Code a pedido do usuário. Achados completos preservados
fora deste documento (relatório enviado ao chat de acompanhamento); resumo dos
achados que geraram ação:

- **Crítico:** `db_get` inexistente em `api/main.py:590`, acionado
  exatamente no caminho de erro do double-submit → `NameError` em produção.
- **Alto:** `db_update` retorna sucesso mesmo com zero linhas afetadas →
  proteção de double-submit não bloqueia de fato.
- **Alto:** `BackgroundTask` no hub para e-mail de link ao parceiro — hub
  confirmado em Render free tier em 2026-07-23, mesmo risco de silenciosa
  falta de entrega documentado na decisão 6.3 para o fichas.
- Demais achados (segurança média/baixa, código morto, dívida técnica)
  distribuídos nas Fases 1, 1B e no roadmap de stand-by (seção 8).

**Decisão registrada:** correções entram em duas fases sequenciais — Fase 1
(`velinn-fichas`, isolada) primeiro, testada e aprovada manualmente; só então
Fase 1B (`velinn-hub`). Nenhuma correção nasce misturada com investigação —
a auditoria em si não alterou nenhuma linha de código.

---

*Este SPEC.md é retroativo e deve ser corrigido pelo Claude Code na próxima
sessão real de trabalho (seções 3 e 7 marcadas como pendentes de validação
linha a linha). A partir desta versão, toda decisão nova segue o padrão da
seção 4.2 do `FRAMEWORK_PROJETOS_CLAUDE_CODE.md`: nova subseção em "6. Decisões
registradas", no momento em que for tomada.*
