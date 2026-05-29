#!/usr/bin/env python3
"""Synchronous HTTP shim that lets the Rotom Dex Lab UI talk to a Hermes agent.

Davi's chat (in the Rotom Dex Lab web UI on his Windows PC) needs to reach a real
Hermes *agent* — the ``rotom-dex`` profile — hosted on the Hermes server. Hermes
has no built-in synchronous "ask the agent and get the reply" HTTP endpoint
(``proxy`` is a raw-model passthrough, ``webhook`` is event-driven/async, ``acp``
is stdio for editors). This tiny, dependency-free service fills that gap.

It exposes, on the LAN:

    GET  /health            -> {"ok": true, "profile": "rotom-dex", "vision": bool}
    POST /chat              -> {"reply": str, "suggestedActions": [...], "offline": false}

Routing:
  * Text         -> ``hermes -z --profile <profile> --continue <session>`` (agent,
                    with conversation memory).
  * With image   -> the local Hermes OpenAI-compatible ``proxy`` (a vision-capable
                    model such as xAI Grok), because ``hermes -z`` has no native
                    image input. Vision is OFF until ROTOM_AGENT_VISION_MODEL is set
                    and ``hermes proxy start`` is running; until then an attached
                    image gets an honest "I can't see photos yet" reply.

``POST /chat`` requires a bearer token (``ROTOM_AGENT_TOKEN``).

Run it on the Hermes box (same server as Rosie):

    ROTOM_AGENT_TOKEN=... python3 rotom_agent_server.py

Configuration (environment variables):
    ROTOM_AGENT_TOKEN     required bearer token shared with the Rotom bridge
    ROTOM_AGENT_HOST      listen interface (default 0.0.0.0)
    ROTOM_AGENT_PORT      listen port (default 8770)
    ROTOM_AGENT_PROFILE   Hermes profile to invoke for text (default "rotom-dex")
    ROTOM_AGENT_SESSION   session name for conversation memory (default "rotom-web")
    ROTOM_AGENT_TIMEOUT   per-request agent timeout in seconds (default 150)
    HERMES_BIN            path to the hermes CLI (default ~/.local/bin/hermes)

    # Vision (images) — via the local `hermes proxy` (OpenAI-compatible):
    ROTOM_AGENT_VISION_MODEL    vision model name; EMPTY disables vision (default "")
    ROTOM_AGENT_VISION_URL      proxy chat-completions URL
                                (default http://127.0.0.1:8645/v1/chat/completions)
    ROTOM_AGENT_VISION_TOKEN    bearer for the proxy (any value; the proxy attaches
                                the real provider creds). Default "rotom".
    ROTOM_AGENT_VISION_TIMEOUT  vision request timeout in seconds (default 90)
"""
from __future__ import annotations

import base64
import binascii
import hmac
import json
import os
import subprocess
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = os.environ.get("ROTOM_AGENT_TOKEN", "")
HOST = os.environ.get("ROTOM_AGENT_HOST", "0.0.0.0")
PORT = int(os.environ.get("ROTOM_AGENT_PORT", "8770"))
PROFILE = os.environ.get("ROTOM_AGENT_PROFILE", "rotom-dex")
SESSION = os.environ.get("ROTOM_AGENT_SESSION", "rotom-web")
TIMEOUT = float(os.environ.get("ROTOM_AGENT_TIMEOUT", "150"))
HERMES_BIN = os.environ.get("HERMES_BIN", os.path.expanduser("~/.local/bin/hermes"))

VISION_MODEL = os.environ.get("ROTOM_AGENT_VISION_MODEL", "").strip()
VISION_URL = os.environ.get("ROTOM_AGENT_VISION_URL", "http://127.0.0.1:8645/v1/chat/completions")
VISION_TOKEN = os.environ.get("ROTOM_AGENT_VISION_TOKEN", "rotom")
VISION_TIMEOUT = float(os.environ.get("ROTOM_AGENT_VISION_TIMEOUT", "90"))

ALLOWED_ACTIONS = {
    "arduino.board_list",
    "arduino.compile",
    "arduino.upload",
    "serial.open",
    "diagnostics.open",
    "templates.list",
}
ALLOWED_IMAGE_MIME = {"image/png", "image/jpeg", "image/webp", "image/gif"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
ACTION_PREFIX = "ACTIONS:"

# Friendly, honest fallback when the agent/vision can't read an attached image.
IMAGE_UNAVAILABLE = (
    "Rotom! Ainda não consigo enxergar fotos por aqui, mas me conta com palavras o "
    "que aparece que eu te ajudo! Você também pode clicar nos botões abaixo."
)

# Serialize agent calls: one session must not be entered concurrently.
_AGENT_LOCK = threading.Lock()

PROMPT_TEMPLATE = """Você é o Rotom Dex falando DIRETO com o Davi, de 9 anos, na interface do \
Rotom Dex Lab (Arduino/ESP32). Responda curto, lúdico e em português do Brasil. \
Não peça comandos perigosos; se uma foto mostrar fios/bateria/motor com dúvida, peça para chamar o papai \
e desligar a energia antes de mexer. Se ajudar, termine com UMA linha começando com 'ACTIONS:' listando, \
separadas por vírgula, ações dentre: arduino.board_list, arduino.compile, arduino.upload, serial.open, \
diagnostics.open, templates.list.

Estado do laboratório (pode usar se útil): {context}
Mensagem do Davi: {message}"""

VISION_SYSTEM = (
    "Você é o Rotom Dex, ajudante lúdico em português do Brasil para o Davi, de 9 anos, "
    "que monta projetos com Arduino/ESP32. Olhe a imagem e responda curto, simples e animado. "
    "Se a foto mostrar fios, bateria, motor ou alimentação e houver dúvida, peça para chamar o papai "
    "e desligar a energia antes de mexer. Não afirme polaridade/ligação se a foto estiver ruim. "
    "Se ajudar, termine com UMA linha começando com 'ACTIONS:' listando, separadas por vírgula, ações "
    "dentre: arduino.board_list, arduino.compile, arduino.upload, serial.open, diagnostics.open, templates.list."
)


def _validate_image_data_url(data_url: str) -> str:
    """Validate a base64 data: image URL (type + size). Returns the mime."""
    if not data_url.startswith("data:"):
        raise ValueError("imagem inválida")
    header, b64 = data_url.split(",", 1)
    meta = header[len("data:") :]
    if ";base64" not in meta:
        raise ValueError("imagem precisa ser base64")
    mime = meta.split(";", 1)[0].strip().lower()
    if mime not in ALLOWED_IMAGE_MIME:
        raise ValueError("tipo de imagem não suportado")
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("base64 inválido") from exc
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("imagem vazia ou grande demais")
    return mime


def _split_reply_and_actions(content: str) -> tuple[str, list[dict]]:
    lines = content.splitlines()
    action_types: list[str] = []
    kept: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.upper().startswith(ACTION_PREFIX):
            raw = stripped[len(ACTION_PREFIX) :]
            action_types = [t.strip() for t in raw.split(",") if t.strip()]
        else:
            kept.append(line)
    reply = "\n".join(kept).strip() or "Rotom!"
    seen: set[str] = set()
    actions: list[dict] = []
    for t in action_types:
        if t in ALLOWED_ACTIONS and t not in seen:
            seen.add(t)
            actions.append({"type": t})
    return reply, actions


def _context_text(context: dict) -> str:
    try:
        return json.dumps(context, ensure_ascii=False)[:1500]
    except (TypeError, ValueError):
        return "{}"


def run_agent_text(message: str, context: dict) -> tuple[str, list[dict], bool]:
    """Run the text agent. Returns ``(reply, actions, ok)``; ok=False => no answer."""
    prompt = PROMPT_TEMPLATE.format(context=_context_text(context), message=message or "(sem texto)")
    # NOTE: we deliberately do NOT pass --accept-hooks. The agent's hook approval
    # gate stays on, so a LAN-reachable request can never make the agent silently
    # run an unseen shell hook.
    cmd = [HERMES_BIN, "-z", prompt, "--profile", PROFILE, "--continue", SESSION]
    with _AGENT_LOCK:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    out = (proc.stdout or "").strip()
    if not out:
        return "", [], False
    reply, actions = _split_reply_and_actions(out)
    return reply, actions, True


def describe_image_via_proxy(message: str, image_data_url: str, context: dict) -> tuple[str, list[dict]]:
    """Send the image to the local Hermes proxy (vision model) and parse the reply."""
    text = message.strip() or "O que você vê nesta imagem? Ajude o Davi."
    text = f"{text}\n\nEstado do laboratório: {_context_text(context)}"
    payload = {
        "model": VISION_MODEL,
        "max_tokens": 500,
        "messages": [
            {"role": "system", "content": VISION_SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text},
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            },
        ],
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(VISION_URL, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {VISION_TOKEN}")
    with urllib.request.urlopen(req, timeout=VISION_TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    content_text = data["choices"][0]["message"]["content"]
    if not isinstance(content_text, str) or not content_text.strip():
        raise ValueError("resposta vazia do modelo de visão")
    return _split_reply_and_actions(content_text)


class Handler(BaseHTTPRequestHandler):
    server_version = "RotomAgentShim/1.1"

    def _send(self, code: int, body: dict) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _authed(self) -> bool:
        if not TOKEN:
            return False
        header = self.headers.get("Authorization", "")
        provided = header[7:] if header.startswith("Bearer ") else ""
        return hmac.compare_digest(provided, TOKEN)

    def do_GET(self):  # noqa: N802
        if self.path.rstrip("/") == "/health":
            self._send(200, {"ok": True, "profile": PROFILE, "vision": bool(VISION_MODEL)})
        else:
            self._send(404, {"error": "not found"})

    def _send_image_unavailable(self) -> None:
        self._send(200, {"reply": IMAGE_UNAVAILABLE, "suggestedActions": [], "offline": True})

    def do_POST(self):  # noqa: N802
        if self.path.rstrip("/") != "/chat":
            self._send(404, {"error": "not found"})
            return
        if not self._authed():
            self._send(401, {"error": "token inválido"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._send(400, {"error": "json inválido"})
            return
        message = str(data.get("message", "")).strip()
        image = data.get("imageDataUrl")
        context = data.get("context") if isinstance(data.get("context"), dict) else {}
        has_image = isinstance(image, str) and bool(image)
        if not message and not has_image:
            self._send(400, {"error": "mensagem ou imagem obrigatória"})
            return

        # --- image path: via the local Hermes vision proxy --------------------
        if has_image:
            if not VISION_MODEL:
                self._send_image_unavailable()
                return
            try:
                _validate_image_data_url(image)
                reply, actions = describe_image_via_proxy(message, image, context)
            except Exception:  # noqa: BLE001 — never leak internals; be honest
                self._send_image_unavailable()
                return
            self._send(200, {"reply": reply, "suggestedActions": actions, "offline": False})
            return

        # --- text path: via the rotom-dex agent -------------------------------
        try:
            reply, actions, ok = run_agent_text(message, context)
        except subprocess.TimeoutExpired:
            self._send(200, {
                "reply": "Rotom! Pensei demais e travei. Tenta perguntar de novo, mais curtinho?",
                "suggestedActions": [],
                "offline": True,
            })
            return
        except Exception:  # noqa: BLE001 — never leak internals to a 9-year-old
            self._send(200, {
                "reply": "Rotom! Tive um probleminha pra pensar agora. Tenta de novo?",
                "suggestedActions": [],
                "offline": True,
            })
            return
        if not ok:
            self._send(200, {
                "reply": "Rotom! Tive um soluço aqui, tenta de novo.",
                "suggestedActions": [],
                "offline": True,
            })
            return
        self._send(200, {"reply": reply, "suggestedActions": actions, "offline": False})

    def log_message(self, *args):  # silence default logging (avoid logging bodies/images)
        pass


def main() -> int:
    if not TOKEN:
        print("ERRO: defina ROTOM_AGENT_TOKEN antes de iniciar.", file=sys.stderr)
        return 2
    if not os.path.exists(HERMES_BIN):
        print(f"ERRO: hermes não encontrado em {HERMES_BIN}", file=sys.stderr)
        return 2
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    vision = VISION_MODEL or "desligada"
    print(f"Rotom agent shim ouvindo em {HOST}:{PORT} (profile {PROFILE}, visão: {vision})", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
