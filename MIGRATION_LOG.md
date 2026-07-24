# MIGRATION_LOG.md — Fase I (migração de fichas para fora do velinn-hub)

> Log de execução autônoma das Fases I.3, I.4, I.5 (parcial) e I.6,
> autorizadas em 2026-07-24. Cada seção documenta o que foi implementado,
> os 3 cenários de teste rodados (com resultado) e achados/decisões que
> precisam de validação humana.

---

## Fase I.3 — Listagem, navegador de pastas do Drive, dropdown de gerentes, "Gerar Link" ligado

### O que foi implementado

- `GET /api/admin/fichas` — listagem, filtrada por `gerente_id` quando o usuário não tem `nivel=admin` nem `"fichas_todas"` em `agentes` (mesma regra do hub).
- `GET /api/admin/gerentes` — dropdown de gerentes (`usuarios` com `nivel in (gerente,admin)` e `ativo=true`).
- `GET /api/admin/drive/pastas?folder_id=` — navegador de pastas do Drive, reaproveitando `_drive_service_rw()` já existente (decidi não criar um serviço read-only separado, já que a credencial é a mesma e a diferença de escopo OAuth não muda o que a service account pode fazer de fato).
- **Achado 1 da I.2 resolvido sem tocar no hub**: criei `_lookup_usuario(usuario)` / `_lookup_usuario_por_id(id)`, que consultam a tabela `usuarios` (mesmo projeto Supabase compartilhado com o hub) para resolver `id`/`email` a partir do `usuario`/`id` que vêm no payload do SSO. `/api/admin/me` agora retorna `id` também. **A correção equivalente no hub (`sso_gerar` incluir `"id"` no payload) continua pendente — não mexi no hub.**
- **Achado adicional (não documentado antes)**: o payload do SSO também não carrega `email`. Resolvido pelo mesmo mecanismo — `_lookup_usuario` busca `email` junto.
- `POST /api/admin/fichas/gerar` — endpoint **novo**, autenticado por sessão local (cookie), não pelo `X-Notif-Secret`. Refatorei a lógica de `POST /api/interno/gerar-ficha` para uma função compartilhada `_gerar_ficha_core(...)`, chamada pelos dois endpoints.
  - **Desvio deliberado das instruções originais**: a Fase I.3 pedia para ligar o botão chamando `POST /api/interno/gerar-ficha` diretamente. Não fiz isso — esse endpoint exige o header `X-Notif-Secret`, que nunca pode ser exposto em JavaScript do navegador (qualquer pessoa abrindo o DevTools veria o segredo e poderia forjar chamadas internas, inclusive em `/api/interno/cnpj`). Criei um endpoint irmão autenticado por sessão em vez disso. Registro isso explicitamente por ser uma mudança de escopo não solicitada literalmente, mesmo com a lógica de negócio idêntica.
- `admin.html`: adicionada listagem (tabela + stats + filtros), modal de navegador de pastas do Drive (réplica funcional do widget do hub), dropdown de gerentes, e o botão "Gerar Link" agora chama `/api/admin/fichas/gerar` de verdade (removido o toast "Disponível em breve" da I.2).

### 3 cenários testados

1. **Sucesso** — usuário nível `gerente` gera link: `id` e `email` resolvidos via `_lookup_usuario` (não do SSO), ficha criada, e-mail disparado com o nome do gerente correto. ✅
2. **Erro/permissão negada** — usuário nível `user` sem `"pode_criar_link"` em `agentes` → 403; requisição sem sessão nenhuma → 403. ✅
3. **Borda específica da fase** — listagem: usuário `gerente` recebe filtro `gerente_id=eq.<id>` na query ao Supabase (não vê fichas de outros gerentes); usuário `admin` não recebe esse filtro (vê todas). Confirmado via inspeção dos parâmetros реalmente enviados ao `db_select`. ✅

### Pendências / achados para validação humana

- **Não testado com Supabase real**: todos os testes acima usam mocks de `db_select`/`db_insert`. A suposição de que `velinn-fichas` consegue de fato consultar a tabela `usuarios` (mesmo projeto Supabase, mesma `SUPABASE_SECRET_KEY` com acesso amplo já que RLS está desabilitado) **precisa ser confirmada em produção** — é a primeira vez que este app consulta essa tabela.
- Botões de **PDF** e **CNPJ** (regenerar) na tabela de listagem do hub não foram mencionados em nenhuma fase (I.3 ou I.4) das suas instruções — deixei-os de fora da tabela por enquanto. Vou incluí-los na Fase I.4 junto com editar/log/deletar, já que fazem parte do mesmo grupo de "botões de ação por ficha" e não têm sentido ficarem pra trás sozinhos — mas registro aqui que essa é uma interpretação minha, não uma instrução explícita.
- Correção equivalente no hub (`sso_gerar` incluir `id`) continua pendente — só documentado, não executado (regra 6: mudança no hub = parar e avisar; como resolvi sem precisar mexer lá, não parei, mas deixo registrado).

---

## Fase I.4 — Editar, log, deletar (+ PDF e CNPJ, interpretação registrada na I.3)

### O que foi implementado

- `PATCH /api/admin/fichas/{token}/editar` — versionamento (`versao++`, novo PDF `_V2`, `_V3`...). **Corrigido em relação ao hub**: o hub ainda salva o PDF de edição direto na raiz da pousada (dívida técnica documentada na Fase H, nunca corrigida lá). Aqui, o PDF da nova versão vai para `Documentos/Documentos Velinn/`, resolvendo `pasta_docs`/`pasta_docs_velinn` via `_drive_get_or_create_folder` — mesmo padrão já validado em produção na Fase H (`_pos_submissao`). Confirmei isso explicitamente no teste 1 (ver abaixo).
- `GET /api/admin/fichas/{token}/log` — mesmo filtro `like.token={prefix}%` já usado pelo hub.
- `DELETE /api/admin/fichas/{token}` — com log no formato `token={prefix}` (já corrigido desde a Fase 1B).
- `GET /api/admin/fichas/{token}/pdf` — download de PDF (interpretação minha, registrada na I.3: não estava em nenhuma fase explícita, mas faz parte do mesmo grupo de "botões de ação por ficha").
- `POST /api/admin/fichas/{token}/cnpj` — regeneração de CNPJ/QSA autenticada por sessão (mesma interpretação). Extraí `_cnpj_core(cnpj, folder_id)` de `/api/interno/cnpj` para reaproveitar a lógica sem duplicar código, igual fiz com `_gerar_ficha_core` na I.3.
- **Permissões replicadas fielmente do hub, inclusive uma inconsistência que já existia lá**: `download_pdf` e `regenerar_cnpj` no hub checam só `_tem_acesso_fichas` (acesso geral), não os flags granulares `fichas_pdf`/`fichas_cnpj` — mesmo o frontend condicionando a exibição dos botões a esses flags. Repliquei esse comportamento exatamente como está (`_admin_tem_acesso_fichas` nos dois), para não mudar comportamento de acesso durante uma migração. Não é uma correção que me pediram, então não a fiz por conta própria — só registro que a inconsistência existe e sobrevive na migração.
- `admin.html`: modais de Editar e Log (réplica funcional dos modais do hub), botões PDF/CNPJ/Editar/Log/Excluir na tabela, todos condicionados aos flags corretos vindos de `/api/admin/me`.

### 3 cenários testados

1. **Sucesso** — edição de ficha: nova versão (`v1→v2`) confirmada, e o PDF da nova versão foi parar em `Documentos Velinn` (pasta `velinn_id`), **não** na raiz (`root_id`) nem em `Documentos Hotel` — validação direta do requisito mais crítico desta fase. ✅
2. **Erro/permissão negada** — usuário sem `fichas_deletar` bloqueado em `DELETE`; usuário sem `fichas_log` bloqueado em `GET .../log`. ✅
3. **Borda específica da fase** — tentativa de baixar PDF de uma ficha com `status="pendente"` → 404 (só fichas preenchidas podem gerar PDF, evita gerar PDF de dados vazios/incompletos). ✅

### Pendências / achados para validação humana

- Mesma ressalva da I.3: testes rodados só com mocks, sem Supabase/Drive reais.
- ~~A inconsistência de permissão (PDF/CNPJ checando acesso geral em vez do flag granular) foi **replicada, não corrigida**~~ — **resolvida em duas correções de segurança separadas (pós-I.4)**: primeiro com um bypass para `nivel=admin` (`_admin_tem_perm_ou_admin`), depois **revertido** — o bypass contradizia a decisão 6.8 do SPEC.md (admin não tem passe livre automático para ações sensíveis; mesmo princípio já aplicado a `deletar`/`log`). Estado final: `GET /api/admin/fichas/{token}/pdf` e `POST /api/admin/fichas/{token}/cnpj` exigem `"fichas_pdf"`/`"fichas_cnpj"` em `agentes`, **sem exceção nenhuma**, nem para admin — usando `_admin_tem_perm` diretamente, igual `deletar`/`editar`/`log`. Essa correção **não foi replicada no hub** — o hub ainda usa `_tem_acesso_fichas` (acesso geral) nos endpoints equivalentes de `regenerar_cnpj`/`download_pdf`; se quiser paridade, precisa entrar na lista de pendências da sessão do hub (seção I.5 acima).

---

## Fase I.5 (parcial) — pendências no `velinn-hub`, NÃO executadas

> Nada nesta seção foi aplicado. `velinn-hub` não foi tocado em nenhum
> momento desta sessão. Isto é só o levantamento detalhado, pra virar uma
> sessão separada com você quando decidir.

### 1. Mudança de URL na tabela `quadros` (Supabase) — requer sua autorização explícita, ainda não dada

O card "Fichas" no painel `/agentes` do hub tem hoje `url = /fichas` (rota interna do hub). Precisa mudar para `https://velinn-fichas.onrender.com/admin` para o handshake de SSO ser acionado (o hub só injeta `?sso=` em URLs que não começam com `/`, conforme o `agentes.html`). **Não fiz essa mudança** — combinado desde o início desta sessão que isso exige autorização separada seguindo, mesmo em modo autônomo.

### 2. Rotas do hub que ficam redundantes (endpoints com equivalente pronto em `velinn-fichas`)

Seguras para remover **depois** que a URL do `quadros` for trocada e você validar que o painel novo funciona de ponta a ponta:

| Rota no hub | Linha (`hub/api/main.py`) | Equivalente em `velinn-fichas` |
|---|---|---|
| `GET /fichas` (serve `fichas.html`) | 971 | `GET /admin` |
| `GET /api/fichas` | 981 | `GET /api/admin/fichas` |
| `GET /api/fichas/gerentes` | 995 | `GET /api/admin/gerentes` |
| `GET /api/drive/pastas` | 888 | `GET /api/admin/drive/pastas` |
| `POST /api/fichas/gerar` | 1004 | `POST /api/admin/fichas/gerar` (já delegava pro fichas desde a I.1b, mas fica redundante com o front novo) |
| `PATCH /api/fichas/{token}/editar` | 1129 | `PATCH /api/admin/fichas/{token}/editar` |
| `POST /api/fichas/{token}/cnpj` | 1163 | `POST /api/admin/fichas/{token}/cnpj` |
| `GET /api/fichas/{token}/log` | 1193 | `GET /api/admin/fichas/{token}/log` |
| `DELETE /api/fichas/{token}` | 1202 | `DELETE /api/admin/fichas/{token}` |
| `GET /api/fichas/{token}/pdf` | 1834 | `GET /api/admin/fichas/{token}/pdf` |

### 3. Código órfão que pode ser removido junto

- `_enviar_email_link_cliente` (linha 1061) — órfã desde a Fase I.1b, nunca removida (decisão explícita na época: dívida técnica pra I.5).
- `_gerar_pdf` (linha 73) e `_upload_drive` (linha 1108) — **confirmei que são usadas exclusivamente pelas rotas de fichas acima** (`editar_ficha` e `download_pdf`), nenhum outro recurso do hub (checklist, parceiro, etc.) depende delas. Seguras para remover junto.

### 4. ⚠️ O que NÃO pode ser removido — compartilhado com outras partes do hub

Investiguei linha por linha antes de listar qualquer coisa como "órfã", e encontrei dependências cruzadas importantes que **não são exclusivas de fichas**:

- **`GET /api/fichas/lista-simples`** (linha 919) — usado por `checklist.html:472` (`fetch('/api/fichas/lista-simples')`). É uma dependência do módulo de **checklist**, não de fichas. **Não remover.**
- **`_drive_service()`** (linha 877, a versão read-only) — usada por `listar_pastas` (linha 895, órfã, ok remover a rota) **e também por `GET /api/drive/folders`** (linha 1786), que é compartilhado entre fichas e checklist (`_tem_acesso_fichas(s) or _tem_acesso_checklist(s)`, linha 1782). **A função em si tem que ficar** — só a rota `/api/drive/pastas` (que só fichas usava) é que é redundante.
- **`_tem_acesso_fichas`, `_pode_criar_link`, `_pode_editar_ficha`, `_tem_perm`** (linhas 950-968) — usadas não só nas rotas de fichas, mas também em `/auth/me` (linha 470-483) e num segundo endpoint `GET /api/me` (linha 1809-1829, aparentemente uma duplicata do `/auth/me` que também devolve flags de checklist) e em `/api/drive/folders` (compartilhado com checklist). **Essenciais, não remover.**
- `GET /api/fichas/notif-emails` (linha 940) — usado pelo `velinn-fichas` (`_enviar_email_notificacao` chama isso via `X-Notif-Secret` pra saber quem notificar). **Não remover** — é contrato ativo entre os dois apps, nada a ver com esta migração de UI.

### 5. Resumo do que a sessão do hub precisaria fazer

1. Trocar a URL do card "Fichas" em `quadros` (autorização sua, específica).
2. Validar em produção que `/admin?sso=...` funciona ponta a ponta.
3. Remover as 10 rotas da tabela do item 2.
4. Remover `_enviar_email_link_cliente`, `_gerar_pdf`, `_upload_drive`.
5. **Não tocar** em `_drive_service()`, `_tem_acesso_fichas`/`_pode_criar_link`/`_pode_editar_ficha`/`_tem_perm`, `/api/fichas/lista-simples`, `/api/fichas/notif-emails`, `/api/drive/folders`, `/api/me`, `/auth/me` — todos compartilhados com outras partes do hub (checklist, parceiro, ou contrato ativo com o fichas).
6. Resolver o Achado 1 original da I.2 no hub (`sso_gerar` incluir `"id"` no payload) — hoje contornado do lado do fichas via lookup direto no Supabase, mas ainda vale corrigir na origem por princípio.

---

## Fase I.6 — Logo/favicon nos lugares restantes

### O que foi implementado

- `cadastro.html`: `<link rel="icon">` trocado de `/favicon.svg` para `/static/favicon.png`; `<img>` do topo trocado de `/logo` para `/static/logo.png`.
- Os 3 templates de e-mail (`_enviar_email_link_cliente`, `_enviar_email_agradecimento`, `_enviar_email_notificacao`) trocados de `https://velinn-fichas.onrender.com/logo` para `https://velinn-fichas.onrender.com/static/logo.png` (mantive URL absoluta — obrigatório para imagens funcionarem dentro de e-mail, relativo não funciona em cliente de e-mail).
- Confirmei via `grep` recursivo que **nenhuma referência** a `/logo` ou `/favicon.svg` (rotas antigas) restava em nenhum arquivo do projeto antes de remover.
- Removidos: `logo.png` e `favicon.svg` da raiz do projeto (arquivos físicos antigos).
- **Decisão corolário, não pedida explicitamente mas consequência direta**: removi também as rotas `GET /logo` e `GET /favicon.svg` de `api/main.py` — elas ficariam servindo `FileResponse` para arquivos que não existem mais (erro 500 em runtime), então deixá-las órfãs seria pior do que removê-las. Nenhuma outra rota ou arquivo as referenciava.

### 3 cenários testados

Nesta fase não há modelo de permissão (são arquivos estáticos e templates de e-mail, sem autenticação) — o cenário "erro/permissão negada" da regra 3 não se aplica de forma natural aqui. Substituí por dois cenários de borda distintos, registrando essa adaptação explicitamente:

1. **Sucesso** — inspecionei o código-fonte das 3 funções de e-mail: todas usam `static/logo.png`, nenhuma ainda referencia o `/logo` antigo. ✅
2. **Borda 1** — inspecionei as rotas registradas no app (`app.routes`): `/logo` e `/favicon.svg` não existem mais; `/static/logo.png` e `/static/favicon.png` existem. ✅
3. **Borda 2** — confirmei que os arquivos físicos novos existem em `static/` (não são referências quebradas) e que os arquivos antigos (`logo.png`, `favicon.svg` na raiz) foram de fato removidos do disco, não só desreferenciados. ✅

### Pendências / achados para validação humana

- Nenhuma. Esta fase não tem dependência de Supabase/Drive real — a verificação mais importante (arquivos existem fisicamente, rotas certas registradas) já foi feita de forma determinística, não por mock.
- Vale conferir visualmente em produção que o logo carrega corretamente nos 3 e-mails (Gmail às vezes cacheia imagens por remetente/domínio de forma imprevisível) e no favicon da aba do navegador em `cadastro.html`.

---

