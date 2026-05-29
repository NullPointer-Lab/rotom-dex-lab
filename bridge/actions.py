from __future__ import annotations

from typing import Any

# Internal action contract shared between backend and frontend.
#
# An action object looks like:
#   {"type": "arduino.compile", "label": "Testar o código agora",
#    "requiresConfirmation": false, "params": {}}
#
# `requiresConfirmation` is ALWAYS taken from this table, never from an AI
# backend, so a remote agent can never silently disable the upload guard.
ALLOWED_ACTIONS: dict[str, dict[str, Any]] = {
    "arduino.board_list": {
        "label": "Procurar minha placa",
        "requiresConfirmation": False,
    },
    "arduino.compile": {
        "label": "Testar o código agora",
        "requiresConfirmation": False,
    },
    "arduino.upload": {
        "label": "Enviar para a placa",
        "requiresConfirmation": True,
    },
    "serial.open": {
        "label": "Abrir o monitor da placa",
        "requiresConfirmation": False,
    },
}


def normalize_action(raw: Any) -> dict[str, Any] | None:
    """Validate a single action object coming from chat/AI backend.

    Returns a clean action dict or None when the action type is unknown.
    """
    if not isinstance(raw, dict):
        return None
    action_type = raw.get("type")
    spec = ALLOWED_ACTIONS.get(action_type)
    if spec is None:
        return None
    label = raw.get("label")
    if not isinstance(label, str) or not label.strip():
        label = spec["label"]
    params = raw.get("params")
    if not isinstance(params, dict):
        params = {}
    return {
        "type": action_type,
        "label": label.strip(),
        "requiresConfirmation": spec["requiresConfirmation"],
        "params": params,
    }


def normalize_actions(raw_actions: Any) -> list[dict[str, Any]]:
    """Normalize a list of actions, dropping unknown ones and duplicates."""
    if not isinstance(raw_actions, list):
        return []
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_actions:
        action = normalize_action(raw)
        if action is None or action["type"] in seen:
            continue
        seen.add(action["type"])
        result.append(action)
    return result


def local_actions_for(message: str) -> list[dict[str, Any]]:
    """Keyword-based safe action suggestions used in offline mode."""
    lower = message.lower()
    types: list[str] = []
    if any(word in lower for word in ("placa", "porta", "conect", "achar", "procur")):
        types.append("arduino.board_list")
    if any(word in lower for word in ("compil", "testa", "test", "build", "erro")):
        types.append("arduino.compile")
    if any(word in lower for word in ("upload", "enviar", "gravar", "subir", "manda")):
        types.append("arduino.upload")
    if any(word in lower for word in ("serial", "monitor", "mensagem", "ver o que")):
        types.append("serial.open")
    if not types:
        types = ["arduino.board_list", "arduino.compile"]
    return normalize_actions([{"type": t} for t in types])
