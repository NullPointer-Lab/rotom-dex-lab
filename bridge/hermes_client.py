from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx

from .actions import local_actions_for, normalize_actions

OFFLINE_REPLY = (
    "Rotom! Posso te ajudar pelos botões: procurar placa, testar o código, enviar para a placa, "
    "abrir serial, rodar o diagnóstico do papai ou mostrar templates seguros."
)
ERROR_REPLY = (
    "Tive um problema para falar com o meu cérebro online agora, mas ainda posso "
    "te ajudar com os botões aqui embaixo."
)


def local_reply_for(message: str) -> str:
    """Return a friendly local-mode reply instead of repeating one generic offline line."""
    lower = message.lower().strip()
    compact = lower.strip("!?. ,;:-")
    if compact in {"oi", "ola", "olá", "e ai", "e aí", "bom dia", "boa tarde", "boa noite"}:
        return (
            "Oi, Davi! Rotom! Para começar, clique em Começar e eu procuro sua placa. "
            "Também posso testar seu projeto, abrir o serial, mostrar templates seguros "
            "ou chamar o diagnóstico do papai."
        )
    if any(word in lower for word in ("diagn", "papai", "status", "saúde", "saude")):
        return "Rotom! Clique em Diagnóstico do papai para eu conferir placa, Arduino CLI, sketch e serial."
    if any(word in lower for word in ("template", "sketch", "exemplo", "motor")):
        return "Rotom! Posso mostrar templates seguros de sketch para você começar sem comandos perigosos."
    if any(word in lower for word in ("placa", "porta", "conect", "achar", "procur")):
        return "Rotom! Clique em Procurar placa e eu tento achar a porta certa para usar."
    if any(word in lower for word in ("compil", "testa", "test", "build", "erro")):
        return "Rotom! Clique em Testar código que eu compilo o projeto e explico qualquer erro do jeito mais fácil."
    if any(word in lower for word in ("upload", "enviar", "gravar", "subir", "manda")):
        return "Rotom! Posso enviar para a placa depois que você confirmar a porta certa."
    if any(word in lower for word in ("serial", "monitor", "mensagem", "ver o que")):
        return "Rotom! Clique em Abrir serial para ver o que a placa está falando."
    return OFFLINE_REPLY


@dataclass
class HermesReply:
    reply: str
    suggested_actions: list[dict[str, Any]] = field(default_factory=list)
    offline: bool = False


class HermesClient:
    """Client for the configurable Rotom Dex / Hermes chat backend.

    Configuration comes from environment variables:
      - ROTOM_DEX_HERMES_URL              backend endpoint (POST JSON)
      - ROTOM_DEX_HERMES_TOKEN            optional bearer token
      - ROTOM_DEX_HERMES_TIMEOUT_SECONDS  optional request timeout (default 20)

    When no URL is configured, or the backend is unreachable/errors, the client
    returns an explicit offline reply and never pretends the real agent answered.
    """

    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
        timeout_seconds: float | None = None,
        transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None,
    ):
        self.url = url if url is not None else os.environ.get("ROTOM_DEX_HERMES_URL") or None
        self.token = token if token is not None else os.environ.get("ROTOM_DEX_HERMES_TOKEN") or None
        if timeout_seconds is not None:
            self.timeout_seconds = timeout_seconds
        else:
            self.timeout_seconds = float(os.environ.get("ROTOM_DEX_HERMES_TIMEOUT_SECONDS", "20"))
        self._transport = transport

    @property
    def configured(self) -> bool:
        return bool(self.url)

    async def send_message(self, message: str, context: dict[str, Any]) -> HermesReply:
        if not self.configured:
            return HermesReply(
                reply=local_reply_for(message),
                suggested_actions=local_actions_for(message),
                offline=True,
            )

        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        payload = {"message": message, "context": context}
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, transport=self._transport
            ) as client:
                response = await client.post(self.url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
        except Exception:
            return HermesReply(
                reply=ERROR_REPLY,
                suggested_actions=local_actions_for(message),
                offline=True,
            )

        reply = data.get("reply") if isinstance(data, dict) else None
        if not isinstance(reply, str) or not reply.strip():
            reply = "Pronto!"
        raw_actions = None
        if isinstance(data, dict):
            raw_actions = data.get("suggestedActions")
            if raw_actions is None:
                raw_actions = data.get("suggested_actions")
        return HermesReply(
            reply=reply.strip(),
            suggested_actions=normalize_actions(raw_actions),
            offline=False,
        )
