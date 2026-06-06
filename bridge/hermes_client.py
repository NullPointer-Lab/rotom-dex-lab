from __future__ import annotations

import asyncio
import json
import os
import shutil
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
LOCAL_CLI_ERROR_REPLY = (
    "Rotom! Meu chat local não respondeu agora. Peça ajuda ao papai para conferir "
    "se o comando rotom está funcionando no terminal."
)

SITE_PROMPT_TEMPLATE = """Você é o Rotom Dex falando DIRETO com o Davi em um site de chat local, estilo Telegram.
Fale em português do Brasil, com energia de Pokédex/Rotom: animado, educativo e curto.
Davi está aprendendo programação, Linux, Arduino/ESP32, robótica e projetos maker.

Regras de segurança:
- Não mexa em contas, compras, redes sociais, Home Assistant, Spotify ou automações externas.
- Para fios, bateria, motor, solda ou energia: peça supervisão do papai antes de mexer.
- Ensine em passos pequenos. Se for explicar código, mostre um pedacinho por vez.
- Responda como conversa normal. Não invente que executou algo.

Se uma ação do laboratório ajudaria, você pode terminar com uma linha opcional:
ACTIONS: arduino.board_list, arduino.compile, serial.open, diagnostics.open, templates.list
Use somente essas ações quando fizer sentido.

Contexto recente do site:
{context}

Mensagem nova do Davi: {message}"""


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "sim", "on"}


def _clean_cli_output(output: str) -> str:
    lines: list[str] = []
    for line in (output or "").splitlines():
        if line.strip().startswith("session_id:"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _split_reply_and_actions(content: str) -> tuple[str, list[dict[str, Any]]]:
    lines: list[str] = []
    raw_actions: list[str] = []
    for line in (content or "").splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("ACTIONS:"):
            raw_actions = [item.strip() for item in stripped[len("ACTIONS:") :].split(",") if item.strip()]
        else:
            lines.append(line)
    reply = "\n".join(lines).strip()
    return reply, normalize_actions([{"type": action} for action in raw_actions])


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
      - ROTOM_DEX_HERMES_LOCAL_CLI=1      call local rotom/hermes CLI when no URL is set
      - ROTOM_DEX_HERMES_BIN              CLI binary for local mode (default rotom/hermes on PATH)

    When no URL is configured, local CLI mode is disabled, or the backend is
    unreachable/errors, the client returns an explicit offline reply and never
    pretends the real agent answered.
    """

    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
        timeout_seconds: float | None = None,
        transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None,
        local_cli: bool | None = None,
        hermes_bin: str | None = None,
    ):
        self.url = url if url is not None else os.environ.get("ROTOM_DEX_HERMES_URL") or None
        self.token = token if token is not None else os.environ.get("ROTOM_DEX_HERMES_TOKEN") or None
        if timeout_seconds is not None:
            self.timeout_seconds = timeout_seconds
        else:
            self.timeout_seconds = float(os.environ.get("ROTOM_DEX_HERMES_TIMEOUT_SECONDS", "20"))
        self._transport = transport
        self.local_cli = _env_truthy("ROTOM_DEX_HERMES_LOCAL_CLI") if local_cli is None else local_cli
        configured_bin = hermes_bin or os.environ.get("ROTOM_DEX_HERMES_BIN")
        self.hermes_bin = configured_bin or shutil.which("rotom") or shutil.which("hermes") or "rotom"

    @property
    def configured(self) -> bool:
        return bool(self.url or self.local_cli)

    async def send_message(self, message: str, context: dict[str, Any]) -> HermesReply:
        if self.url:
            return await self._send_http(message, context)
        if self.local_cli:
            return await self._send_local_cli(message, context)
        return HermesReply(
            reply=local_reply_for(message),
            suggested_actions=local_actions_for(message),
            offline=True,
        )

    async def _send_http(self, message: str, context: dict[str, Any]) -> HermesReply:
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

    async def _send_local_cli(self, message: str, context: dict[str, Any]) -> HermesReply:
        try:
            context_json = json.dumps(context or {}, ensure_ascii=False, indent=2)[:5000]
        except TypeError:
            context_json = "{}"
        prompt = SITE_PROMPT_TEMPLATE.format(context=context_json, message=message.strip())
        toolsets = os.environ.get("ROTOM_DEX_HERMES_TOOLSETS", "safe")
        cmd = [self.hermes_bin, "chat", "-q", prompt, "--toolsets", toolsets, "-Q"]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout_seconds)
        except Exception:
            return HermesReply(
                reply=LOCAL_CLI_ERROR_REPLY,
                suggested_actions=local_actions_for(message),
                offline=True,
            )

        if proc.returncode != 0:
            return HermesReply(
                reply=LOCAL_CLI_ERROR_REPLY,
                suggested_actions=local_actions_for(message),
                offline=True,
            )
        content = _clean_cli_output(stdout.decode("utf-8", errors="replace"))
        reply, actions = _split_reply_and_actions(content)
        return HermesReply(reply=reply or "Rotom!", suggested_actions=actions, offline=False)
