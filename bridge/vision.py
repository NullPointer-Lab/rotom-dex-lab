from __future__ import annotations

import base64
import binascii
import os
from typing import Any

import httpx

from .actions import local_actions_for, normalize_actions
from .hermes_client import ERROR_REPLY, HermesReply, local_reply_for

# Allowed pasted/attached image types and a conservative size cap. The image is
# forwarded to the Hermes agent and never written to disk or logged on this side.
ALLOWED_IMAGE_MIME = {"image/png", "image/jpeg", "image/webp", "image/gif"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB


class ImageError(ValueError):
    """Raised when an attached image is missing, malformed, or not allowed.

    Subclasses ValueError so the API layer can turn it into a friendly 400.
    """


def parse_image_data_url(data_url: str) -> tuple[str, bytes]:
    """Validate a base64 ``data:`` image URL and return ``(mime, raw_bytes)``.

    Accepts only base64-encoded data URLs of an allowed image type, within the
    size limit. Raises :class:`ImageError` on anything else.
    """
    if not isinstance(data_url, str) or not data_url.strip():
        raise ImageError("Não recebi a imagem. Tente colar ou anexar a foto de novo.")
    if not data_url.startswith("data:"):
        raise ImageError("Formato de imagem não reconhecido. Cole uma foto ou um print.")
    try:
        header, b64 = data_url.split(",", 1)
    except ValueError as exc:
        raise ImageError("A imagem veio incompleta. Tente anexar de novo.") from exc
    meta = header[len("data:") :]
    if ";base64" not in meta:
        raise ImageError("Só consigo ler imagem colada ou anexada (base64).")
    mime = meta.split(";", 1)[0].strip().lower()
    if mime not in ALLOWED_IMAGE_MIME:
        raise ImageError("Esse arquivo não é uma imagem que eu entendo. Use PNG, JPG, WEBP ou GIF.")
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ImageError("Não consegui ler a imagem. Tente tirar ou colar a foto de novo.") from exc
    if not raw:
        raise ImageError("A imagem veio vazia. Tente de novo.")
    if len(raw) > MAX_IMAGE_BYTES:
        mb = MAX_IMAGE_BYTES // (1024 * 1024)
        raise ImageError(f"A imagem é grande demais (máximo {mb} MB). Tire uma foto menor.")
    return mime, raw


def _local_multimodal_reply(message: str, has_image: bool) -> str:
    if has_image:
        return (
            "Rotom! Recebi sua imagem 📷. Meu olho mágico (modo visão) ainda não está ligado "
            "aqui, então me conte com palavras o que aparece — ou clique num botão que eu já "
            "sei usar, tipo Procurar placa ou Testar código."
        )
    return local_reply_for(message)


class VisionClient:
    """Image-aware chat client that talks to the Hermes ``rotom-dex`` agent.

    It speaks the same simple protocol as :class:`~bridge.hermes_client.HermesClient`
    (POST JSON ``{message, context, imageDataUrl?}`` -> ``{reply, suggestedActions,
    offline}``), pointed at the Hermes agent HTTP shim. By default it reuses the
    text-chat configuration so a single endpoint/token drives the whole chat brain:

      - ROTOM_DEX_VISION_URL    (falls back to ROTOM_DEX_HERMES_URL)
      - ROTOM_DEX_VISION_TOKEN  (falls back to ROTOM_DEX_HERMES_TOKEN)
      - ROTOM_DEX_VISION_TIMEOUT_SECONDS (falls back to ROTOM_DEX_HERMES_TIMEOUT_SECONDS, then 120)

    When no URL is configured, or the backend errors, it returns an explicit,
    honest local reply and never pretends a real agent answered.
    """

    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
        timeout_seconds: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.url = url if url is not None else (
            os.environ.get("ROTOM_DEX_VISION_URL")
            or os.environ.get("ROTOM_DEX_HERMES_URL")
            or None
        )
        self.token = token if token is not None else (
            os.environ.get("ROTOM_DEX_VISION_TOKEN")
            or os.environ.get("ROTOM_DEX_HERMES_TOKEN")
            or None
        )
        if timeout_seconds is not None:
            self.timeout_seconds = timeout_seconds
        else:
            self.timeout_seconds = float(
                os.environ.get(
                    "ROTOM_DEX_VISION_TIMEOUT_SECONDS",
                    os.environ.get("ROTOM_DEX_HERMES_TIMEOUT_SECONDS", "120"),
                )
            )
        self._transport = transport

    @property
    def configured(self) -> bool:
        return bool(self.url)

    async def describe(
        self,
        message: str,
        image_data_url: str | None,
        context: dict[str, Any] | None = None,
    ) -> HermesReply:
        has_image = bool(image_data_url)
        if not self.configured:
            return HermesReply(
                reply=_local_multimodal_reply(message, has_image),
                suggested_actions=local_actions_for(message),
                offline=True,
            )

        payload: dict[str, Any] = {"message": message, "context": context or {}}
        if has_image:
            payload["imageDataUrl"] = image_data_url
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, transport=self._transport
            ) as client:
                response = await client.post(self.url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
            reply = data.get("reply") if isinstance(data, dict) else None
            if not isinstance(reply, str) or not reply.strip():
                raise ValueError("resposta vazia do agente")
        except Exception:
            return HermesReply(
                reply=ERROR_REPLY,
                suggested_actions=local_actions_for(message),
                offline=True,
            )

        raw_actions = data.get("suggestedActions")
        if raw_actions is None:
            raw_actions = data.get("suggested_actions")
        return HermesReply(
            reply=reply.strip(),
            suggested_actions=normalize_actions(raw_actions),
            offline=bool(data.get("offline", False)),
        )
