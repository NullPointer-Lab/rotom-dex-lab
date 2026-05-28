from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class HermesReply:
    reply: str
    suggested_actions: list[dict[str, Any]]


class HermesClient:
    """Placeholder client for the future Rotom Dex Hermes profile integration.

    The real implementation should call the Hermes API/webhook for profile `rotom-dex`.
    Keeping this as a safe stub lets the Windows UI work before credentials/network are added.
    """

    async def send_message(self, message: str, context: dict[str, Any]) -> HermesReply:
        lower = message.lower()
        actions: list[dict[str, Any]] = []
        if "placa" in lower or "porta" in lower or "com" in lower:
            actions.append({"type": "arduino.board_list", "requiresConfirmation": False, "params": {}})
        if "compil" in lower or "build" in lower:
            actions.append({"type": "arduino.compile", "requiresConfirmation": True, "params": {}})
        if "upload" in lower or "enviar" in lower or "gravar" in lower:
            actions.append({"type": "arduino.upload", "requiresConfirmation": True, "params": {}})

        return HermesReply(
            reply=(
                "Rotom Dex online! Por enquanto estou no modo bridge local. "
                "Posso ajudar a listar a placa, compilar, preparar upload e ler serial com segurança."
            ),
            suggested_actions=actions,
        )
