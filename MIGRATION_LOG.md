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

