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

## Integração com ClickUp (acompanhamento de projeto)

- O projeto tem uma estrutura no ClickUp (Espaço "Projetos VELINN" → Pasta
  "VELINN Fichas" → Listas "Roadmap & Pendências" e "Histórico (Concluído)"),
  mesmo padrão já usado pelo `velinn-hub`.
- **Identificação de tarefa é SEMPRE por ID/link explícito, nunca por
  similaridade de nome.** Ao trabalhar numa fase que corresponde a uma
  tarefa do ClickUp, o ID da tarefa deve ser informado explicitamente
  (pelo usuário ou já presente no contexto) — nunca tente adivinhar qual
  tarefa corresponde a um commit só pelo texto da mensagem.
- Referencie o ID da tarefa no trailer do commit quando aplicável, ex:
  `ClickUp-Task: 86e2jk0f2`.
- Você PODE, via API do ClickUp (token em `CLICKUP_API_TOKEN`, `.env`,
  nunca commitado): mover o status da tarefa até **"aguardando teste"**, e
  adicionar comentários narrando o progresso (plano aprovado, testes
  rodados, resultado).
- **Você NUNCA marca uma tarefa como "aprovada" sozinho.** Esse status
  exige confirmação explícita do usuário — no chat de acompanhamento ou
  diretamente no ClickUp. Isso vale mesmo que todos os testes tenham
  passado e o commit já tenha sido feito: "aprovada" é uma decisão do
  usuário, não uma consequência automática do código funcionar.
- Se não tiver certeza de qual tarefa corresponde ao trabalho atual, PARE
  e pergunte — não crie uma tarefa nova nem escolha uma por aproximação.

## Deploy no Cloud Run — lições pagas caro pelo velinn-hub, aplicam-se aqui

Estas regras existem porque cada uma já causou um incidente real no
`velinn-hub` (mesma infraestrutura, mesmo ecossistema). Formato de
regra importa: proibição absoluta ou passo obrigatório dentro de um
ciclo — não é sugestão de boa prática.

**REGRA 1 — NUNCA rode `gcloud run deploy` sem flags explícitas de
imagem e env vars.** Um comando sem `--image` herda o digest antigo
do template; um comando com `--image` mas sem `--update-env-vars`
herda o template sem a env var que você quis mudar. O que você não
declara explicitamente na flag não é neutro — é herdado do estado
anterior. Antes de qualquer `gcloud run deploy`/`update`, liste as
flags que serão usadas e confirme que cobrem TODAS as env vars/imagem
relevantes, não só a que você quer mudar.

**REGRA 2 — Antes de qualquer teste que altere configuração do
serviço no Cloud Run (env var, imagem, etc.), siga este ciclo
obrigatório, nesta ordem, sem pular etapa:**
1. Registre o estado atual (`gcloud run services describe`, salve a
   saída) ANTES de mudar qualquer coisa.
2. Faça a mudança de teste.
3. Desfaça a mudança EXPLICITAMENTE (não assuma que `--no-traffic` ou
   deletar a revisão de teste reverte o estado — `--no-traffic`
   protege só o tráfego, não desfaz o template/config do serviço).
4. Rode um `describe` FRESCO (não reaproveite o describe de antes) e
   confirme que o estado bate com o do passo 1.
5. Só então reporte o resultado do teste — nunca reporte "sem
   impacto" tendo verificado apenas o tráfego, sem confirmar o estado
   do template.

**REGRA 3 — env var crítica (sem a qual o app não pode funcionar com
segurança) NÃO deve ter fallback hardcoded para um valor de produção
morto ou adivinhado.** Prefira falhar alto no boot (`raise
RuntimeError` se a env var estiver ausente) a cair silenciosamente
num default desatualizado. Racional: o Cloud Run não migra tráfego
para uma revisão que não sobe — a revisão anterior continua servindo.
Um deploy que falha visivelmente é preferível a um site no ar
servindo dado errado sem ninguém perceber. Isso já é o caso de
`CLICKUP_API_TOKEN` e deve ser avaliado para `HUB_URL` também (ver
tarefa `86e2jvbvp` no ClickUp).

**REGRA 4 — Antes de assumir que uma peça de documentação de processo
existe (CLAUDE.md, SPEC.md, docs/API.md), confirme com `find`/`ls`
real.** Não assuma pela conversa ou pela memória do chat — o
`velinn-hub` rodou meses em produção sem `CLAUDE.md`, com as regras
vivendo só em prompts, e essa foi a causa raiz do drift de
documentação lá.
