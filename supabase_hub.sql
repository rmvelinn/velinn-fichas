-- ============================================================================
-- supabase_hub.sql — Schema das tabelas do Supabase compartilhadas com o
-- velinn-hub (e outros apps do ecossistema VELINN), documentado a partir da
-- introspecção real do PostgREST em 2026-07-24.
--
-- Este arquivo é documentação pura — nenhum ALTER/CREATE aqui foi executado
-- pelo Claude Code. Onde há divergência entre o schema real e o que o
-- código espera, está marcado explicitamente como ACHADO, com o SQL de
-- correção destacado para execução manual.
--
-- Ver também: SPEC.md (seção 4) para o detalhamento funcional de
-- fichas_cadastrais, a única tabela exclusiva do velinn-fichas.
-- ============================================================================


-- ============================================================================
-- usuarios — COMPARTILHADA (hub, fichas, checklist, metas)
-- ============================================================================
-- Cadastro de usuários do ecossistema — login, nível de acesso, permissões
-- granulares (array `agentes`), flags de notificação por módulo.
CREATE TABLE IF NOT EXISTS usuarios (
    id                      uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario                 text        NOT NULL,               -- required
    senha_hash              text        NOT NULL,               -- required
    nivel                   text        DEFAULT 'user',         -- admin | gerente | user | parceiro
    agentes                 text[],                              -- permissões granulares (fichas_link, fichas_pdf, pode_criar_link, ...)
    ativo                   boolean     DEFAULT true,
    criado_em               timestamptz DEFAULT now(),
    nome                    text        DEFAULT '',
    email                   text,
    primeiro_acesso         boolean     DEFAULT true,
    notif_fichas            boolean     DEFAULT false,
    pode_criar_link         boolean     DEFAULT false,
    notif_checklist         boolean     NOT NULL,               -- required (sem default na introspecção)
    pode_editar             boolean     DEFAULT false,
    notif_metas_coleta      boolean     DEFAULT false,
    notif_metas_equipe      boolean     DEFAULT false
);

-- Usada por velinn-fichas via _lookup_usuario()/_lookup_usuario_por_id()
-- (Fase I.3) para resolver id/email do usuário autenticado via SSO, já que
-- o payload do handshake SSO não carrega esses dois campos.


-- ============================================================================
-- sessoes — COMPARTILHADA (hub)
-- ============================================================================
-- Sessões de login do velinn-hub. Backup em disco do cache em memória
-- (_sessao_salvar/_sessao_remover no hub) — não usada pelo velinn-fichas,
-- que tem seu próprio mecanismo de sessão local (_ADMIN_SESSIONS, Fase I.2).
CREATE TABLE IF NOT EXISTS sessoes (
    token                   text        PRIMARY KEY,            -- required
    usuario                 text        NOT NULL,               -- required
    criado_em               timestamptz DEFAULT now()
);


-- ============================================================================
-- logs — COMPARTILHADA (hub, fichas, checklist)
-- ============================================================================
-- Log de auditoria genérico, usado por todos os módulos do ecossistema.
-- velinn-fichas escreve aqui desde a Fase I.1a (helpers db_insert/_log,
-- que não existiam antes disso no repositório do fichas).
CREATE TABLE IF NOT EXISTS logs (
    id                      uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario                 text        NOT NULL,               -- required
    acao                    text        NOT NULL,               -- required
    detalhe                 text        DEFAULT '',
    ip                      text        DEFAULT '',
    criado_em               timestamptz DEFAULT now()
);

-- Convenção usada pelo fichas (e pelo hub, desde a Fase 1B): quando `detalhe`
-- se refere a uma ficha específica, começa com "token={8 primeiros
-- caracteres do token}" — é o que o filtro `like.token=XXXXXXXX%` em
-- GET /api/admin/fichas/{token}/log usa para achar o histórico de uma ficha.


-- ============================================================================
-- quadros — COMPARTILHADA (hub, painel /agentes)
-- ============================================================================
-- Cards exibidos no painel principal do hub (/agentes). Controla nome,
-- ícone, URL de destino e visibilidade de cada app do ecossistema —
-- inclusive o card "Fichas", que hoje aponta para
-- https://velinn-fichas.onrender.com/admin (trocado na Fase I.5).
CREATE TABLE IF NOT EXISTS quadros (
    id                      uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    id_chave                text        NOT NULL,               -- required
    icone                   text        DEFAULT '📊',
    nome                    text        NOT NULL,               -- required
    descricao               text,
    url                     text,
    visibilidade            text        DEFAULT 'ativo',
    status_implantacao      text        DEFAULT 'funcional',
    ordem                   integer     DEFAULT 0,
    criado_em               timestamptz DEFAULT now()
);


-- ============================================================================
-- fichas_cadastrais — EXCLUSIVA do velinn-fichas
-- ============================================================================
-- Schema completo já documentado no SPEC.md (seção 4.1) deste repositório.
-- Reproduzido aqui só para manter os 5 schemas juntos num lugar só.
CREATE TABLE IF NOT EXISTS fichas_cadastrais (
    id                      uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    token                   text        UNIQUE NOT NULL,
    gerente_id              text,
    gerente_nome            text,
    gerente_email           text,
    nome_pousada            text,
    nome_proprietario       text,
    email_proprietario      text,
    drive_folder_id         text,
    status                  text        DEFAULT 'pendente',    -- pendente | preenchido

    -- Dados da empresa
    razao_social            text,
    nome_fantasia           text,
    cnpj                    text,
    endereco                text,
    numero                  text,
    complemento             text,
    bairro                  text,
    cidade                  text,
    estado                  text,
    cep                     text,
    email_administrativo    text,

    -- Dados do sócio
    socio_nome              text,
    socio_data_nascimento   text,
    socio_cpf               text,
    socio_rg                text,
    socio_email             text,
    socio_celular           text,
    socio_endereco          text,
    socio_numero            text,
    socio_complemento       text,
    socio_bairro            text,
    socio_cep               text,
    socio_cidade            text,
    socio_estado            text,

    -- Testemunhas (v2 — array JSONB)
    num_testemunhas         integer     DEFAULT 1,   -- ⚠️ ACHADO — ver nota abaixo, deveria ser 0
    testemunhas              jsonb       DEFAULT '[]',
    -- colunas legado v1 (mantidas por compatibilidade, não usar em código novo):
    -- testemunha_nome/cpf/rg/email/data_nascimento

    -- Resultado
    pdf_drive_url            text,
    cnpj_status               text,       -- ⚠️ PENDENTE — coluna nova (Fase D/Frente 2), ainda não aplicada no banco real
    versao                   integer     DEFAULT 1,

    -- Rastreamento
    visualizado_em           timestamptz,
    criado_em                 timestamptz DEFAULT now(),
    preenchido_em             timestamptz
);


-- ============================================================================
-- ACHADOS — pendentes de execução manual pelo usuário, NÃO aplicados aqui
-- ============================================================================

-- ACHADO 1 — num_testemunhas ainda tem DEFAULT 1 no banco real, confirmado
-- via introspecção em 2026-07-24, apesar do código da aplicação já ter sido
-- corrigido para default 0 em 4 pontos (admin.html, _gerar_ficha_core,
-- cadastro_info, cadastro.html — commit 8bc5fad). Isso só afeta fichas
-- criadas por algum caminho que não passe pelo código da aplicação (ex:
-- insert manual direto no Supabase) — mas a coluna deveria refletir a
-- mesma regra de negócio já corrigida no código.
ALTER TABLE fichas_cadastrais ALTER COLUMN num_testemunhas SET DEFAULT 0;

-- ACHADO 2 — cnpj_status (Frente 2/Fase D, 2026-07-24): coluna nova,
-- necessária para o painel /admin mostrar alerta de falha de upload do
-- CNPJ/QSA. Código já escreve nela (_pos_submissao); sem essa coluna no
-- banco real, o db_update falha silenciosamente (loga erro, não quebra o
-- fluxo, mas o campo nunca é persistido).
ALTER TABLE fichas_cadastrais ADD COLUMN IF NOT EXISTS cnpj_status text DEFAULT NULL;


-- ============================================================================
-- NOTA — família de tabelas do checklist (fora do escopo desta documentação)
-- ============================================================================
-- Existem também: checklists, checklist_steps, checklist_logs,
-- checklist_arquivos, checklist_pdfs — todas no mesmo projeto Supabase,
-- seguindo um padrão de schema similar ao de fichas_cadastrais (token como
-- credencial, versionamento, upload no Drive). Não documentadas aqui por
-- estarem fora do escopo desta Frente — útil registrar a existência delas
-- desde já para quando a migração do velinn-checklist (fora do hub, mesmo
-- espírito da Fase I do fichas) chegar nessa etapa.
