"""Helper de integração com o ClickUp para acompanhamento de projeto.

Estrutura no ClickUp: Espaço "Projetos VELINN" -> Pasta "VELINN Fichas" ->
Listas "Roadmap & Pendências" (901715683600) e "Histórico (Concluído)"
(901715683602).

Regras (ver CLAUDE.md, seção "Integração com ClickUp"):
- Identificação de tarefa é sempre por ID explícito, nunca por similaridade
  de nome — cabe a quem chama este módulo garantir isso.
- Pode mover status até "aguardando teste" e comentar via API.
- NUNCA move uma tarefa para "aprovada" — ver trava em mover_status_tarefa.
"""

import os

import requests

CLICKUP_API_TOKEN = os.environ.get("CLICKUP_API_TOKEN", "")
CLICKUP_BASE_URL = "https://api.clickup.com/api/v2"

STATUS_PROIBIDO = "aprovada"


def _headers() -> dict:
    if not CLICKUP_API_TOKEN:
        raise RuntimeError("CLICKUP_API_TOKEN não configurada")
    return {"Authorization": CLICKUP_API_TOKEN, "Content-Type": "application/json"}


def mover_status_tarefa(task_id: str, novo_status: str) -> dict:
    if not task_id:
        raise ValueError("task_id é obrigatório — identificação sempre por ID explícito")

    if novo_status.strip().lower() == STATUS_PROIBIDO:
        raise PermissionError(
            "Bloqueado: mover uma tarefa para 'aprovada' exige confirmação "
            "explícita do usuário — este helper nunca faz essa transição sozinho."
        )

    r = requests.put(
        f"{CLICKUP_BASE_URL}/task/{task_id}",
        headers=_headers(),
        json={"status": novo_status},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def comentar_tarefa(task_id: str, texto: str) -> dict:
    if not task_id:
        raise ValueError("task_id é obrigatório — identificação sempre por ID explícito")

    r = requests.post(
        f"{CLICKUP_BASE_URL}/task/{task_id}/comment",
        headers=_headers(),
        json={"comment_text": texto},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()
