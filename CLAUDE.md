# CLAUDE.md — VELINN Ficha Cadastral (`velinn-fichas`)

> Lido automaticamente pelo Claude Code no início de toda sessão neste
> repositório. Este projeto já está em produção — as regras abaixo valem para
> qualquer mudança **a partir de agora**, não para o histórico já commitado.

---

## Regra de ouro

- Este projeto segue a especificação em `SPEC.md`.
- Trabalhamos **uma fase por vez** (seção 8 do SPEC.md).
- **NUNCA avance para a fase seguinte sem confirmação explícita do usuário**
  de que testou manualmente e aprovou a fase atual.
- Antes de codar qualquer fase, liste o plano em tópicos e espere aprovação.
- Este sistema tem parceiros reais usando o link em produção — qualquer
  mudança em `velinn-fichas` (público) precisa ser testada localmente/staging
  antes de subir, nunca direto em produção sem aviso.

## Contexto de dois repositórios

- Este `CLAUDE.md` vive em `velinn-fichas`. O painel interno (`velinn-hub`)
  tem seu próprio `CLAUDE.md` e sua própria sessão de Claude Code.
- Se uma fase exigir mudança nos dois repositórios (ex: novo campo na ficha
  que também precisa aparecer no modal de edição do hub), **diga isso
  explicitamente antes de codar** — não assuma que o outro repositório será
  ajustado automaticamente.
- A comunicação entre os dois apps é via header `X-Notif-Secret`
  (`FICHAS_NOTIF_SECRET`). Qualquer mudança nesse contrato interno precisa ser
  sincronizada manualmente nos dois lados.

## Controle de versão (Git)

- Ao final de cada fase aprovada, faça automaticamente um `git add .` e
  `git commit` com mensagem clara descrevendo a entrega.
- **NÃO execute `git push` automaticamente** — isso fica a critério do usuário.
- Nunca faça commit de arquivos sensíveis (`.env`, `DRIVE_SA_JSON`,
  `GMAIL_SA_JSON`, `SUPABASE_SECRET_KEY`, `FICHAS_NOTIF_SECRET`).

## Documentação de API (`docs/API.md`)

- Ao final de cada fase aprovada, atualize `docs/API.md` com os endpoints
  novos ou alterados: método, caminho, autenticação, exemplo real de
  request/response.
- Organize por grupo de recursos (fichas públicas / fichas internas /
  integrações externas).

## Credenciais e segredos — regras que não negociam

- Nenhuma credencial real nova (ClickUp API Key, credencial de gateway,
  qualquer serviço novo) vai para código ou `.env` versionado, nunca.
- Toda integração externa nova (ex: ClickUp, contrato DOCX automatizado) nasce
  com interface plugável + implementação fake até a credencial real existir.
- Avisar explicitamente antes de qualquer commit que possa conter esse tipo de
  dado.
- As credenciais já em uso hoje (`SUPABASE_SECRET_KEY`, `DRIVE_SA_JSON`,
  `GMAIL_SA_JSON`, `FICHAS_NOTIF_SECRET`) já estão configuradas no Render como
  variáveis de ambiente — nunca as imprima em log, nunca as reescreva em texto
  claro em nenhum arquivo do repositório.

## Antes de mexer em fluxo já validado em produção

- Pós-submissão é **síncrono de propósito** (decisão 6.3 do SPEC.md) —
  não converta para background task sem essa decisão ser revisada
  explicitamente com o usuário primeiro.
- Proteção contra double-submit depende de **duas camadas**: flag no
  frontend + `WHERE status=eq.pendente` no PATCH. Não remova nenhuma das
  duas achando que é redundante.
- Deduplicação de e-mail é case-insensitive (`.strip().lower()`) — qualquer
  mudança na lógica de envio de e-mail precisa preservar isso.

## Investigação antes de mudança

- Antes de propor uma correção, confirme a hipótese lendo o código real —
  não assuma comportamento a partir da descrição em `SPEC.md` (que é
  retroativo e pode ter imprecisões, sinalizadas nas seções 3 e 7).
- Se encontrar divergência entre o que o `SPEC.md` descreve e o código real,
  reporte a divergência antes de decidir qual dos dois está certo.
