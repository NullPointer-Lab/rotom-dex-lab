from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager, suppress
from pathlib import Path, PureWindowsPath
from typing import Any

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .arduino import ArduinoService
from .auth import TOKEN_MISSING_MESSAGE, SessionAuth
from .board_parser import simplify_board_list
from . import codegen
from .codegen import CodegenError
from .config import load_config, load_missions, save_mission_status
from .hermes_client import HermesClient
from .policy import PolicyError, _is_windows_style, resolve_sketch_path
from .serial_monitor import SerialError, SerialManager
from .sketch_templates import create_template_file, render_template, template_catalog
from .translate import core_installed, friendly_arduino_message
from .vision import ImageError, VisionClient, parse_image_data_url

ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "web"
MISSIONS_PATH = ROOT / "config" / "missions.json"


def startup_banner(
    *,
    token: str,
    port: int | str,
    hermes_configured: bool,
    arduino_found: bool,
    fake_serial: bool,
) -> list[str]:
    """Lines printed at startup so a human can find the access URL and token.

    Without this, starting the server directly (e.g. ``uvicorn bridge.server:app``)
    produces a random token with no way to discover it, and every action endpoint
    rejects the request. Kept pure so it can be unit-tested.
    """
    url = f"http://127.0.0.1:{port}/?token={token}"
    lines = [
        "==== Rotom Dex Lab ====",
        f"Abra no navegador (neste computador): {url}",
        f"PIN/token de acesso: {token}",
        f"Arduino CLI: {'encontrado' if arduino_found else 'NAO encontrado — instale o arduino-cli'}",
        f"Cerebro online (Hermes): {'configurado' if hermes_configured else 'offline (modo local)'}",
    ]
    if fake_serial:
        lines.append("Monitor serial em MODO SIMULACAO (ROTOM_DEX_FAKE_SERIAL=1).")
    lines.append("Para acesso por outro aparelho na rede, troque 127.0.0.1 pelo IP deste computador.")
    return lines


@asynccontextmanager
async def lifespan(app: FastAPI):
    for line in startup_banner(
        token=auth.token,
        port=os.environ.get("ROTOM_DEX_PORT", "8765"),
        hermes_configured=hermes.configured,
        arduino_found=bool(arduino.runner.find_executable()),
        fake_serial=serial_manager.fake,
    ):
        print(line, flush=True)
    yield


app = FastAPI(title="Rotom Dex Lab", version="0.2.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(WEB_ROOT)), name="static")

config = load_config()
arduino = ArduinoService()
serial_manager = SerialManager()
hermes = HermesClient()
vision = VisionClient()
auth = SessionAuth()


async def require_token(
    x_rotom_token: str | None = Header(default=None),
    token: str | None = Query(default=None),
) -> bool:
    provided = x_rotom_token or token
    if not auth.check(provided):
        raise HTTPException(status_code=401, detail=TOKEN_MISSING_MESSAGE)
    return True


class CompileRequest(BaseModel):
    projectId: str | None = None
    fqbn: str | None = None
    sketchPath: str | None = None


class UploadRequest(CompileRequest):
    port: str
    confirmed: bool = False


class SerialOpenRequest(BaseModel):
    port: str
    baud: int = 115200


class SerialCloseRequest(BaseModel):
    sessionId: str


class SerialWriteRequest(BaseModel):
    sessionId: str
    text: str


class MissionStatusRequest(BaseModel):
    status: str


class TemplateCreateRequest(BaseModel):
    confirmed: bool = False
    projectId: str | None = None


class ChatRequest(BaseModel):
    message: str
    projectId: str | None = None
    context: dict[str, Any] = {}


class ChatMultimodalRequest(BaseModel):
    message: str = ""
    projectId: str | None = None
    imageDataUrl: str | None = None
    context: dict[str, Any] = {}


class VibeRequest(BaseModel):
    instruction: str
    projectId: str | None = None


class CodeRestoreRequest(BaseModel):
    hash: str
    projectId: str | None = None
    confirmed: bool = False


def result_to_dict(result, action: str = "comando"):
    return {
        "args": result.args,
        "exitCode": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "ok": result.exit_code == 0,
        "message": friendly_arduino_message(result, action),
    }


def _sketch_check(project) -> dict[str, Any]:
    if _is_windows_style(project.root) and os.name != "nt":
        path = str(PureWindowsPath(project.root) / project.sketch)
        return {
            "id": "sketchPath",
            "label": "Sketch configurado",
            "ok": None,
            "detail": f"{path} (caminho Windows; existência só é conferida no Windows do Davi)",
        }
    sketch_path = Path(project.root).expanduser() / project.sketch
    return {
        "id": "sketchPath",
        "label": "Sketch configurado",
        "ok": sketch_path.exists(),
        "detail": str(sketch_path),
    }


@app.get("/")
async def index():
    return FileResponse(WEB_ROOT / "index.html")


@app.get("/api/health")
async def health():
    found = arduino.runner.find_executable()
    core_ok = None
    if found:
        project = config.get_project()
        core_result = await arduino.core_list()
        if core_result.exit_code == 0:
            core_ok = core_installed(core_result.stdout, project.defaultFqbn)
    return {
        "ok": True,
        "name": "Rotom Dex Lab",
        "bridgeVersion": app.version,
        "arduinoCliFound": bool(found),
        "arduinoCliPath": found,
        "coreInstalled": core_ok,
        "hermesConfigured": hermes.configured,
        "fakeSerial": serial_manager.fake,
        "projects": [p.model_dump() for p in config.projects],
    }


@app.get("/api/missions", dependencies=[Depends(require_token)])
async def missions():
    return {"missions": load_missions(MISSIONS_PATH)}


@app.post("/api/missions/{mission_id}/status", dependencies=[Depends(require_token)])
async def mission_status(mission_id: str, req: MissionStatusRequest):
    try:
        return {"missions": save_mission_status(mission_id, req.status, MISSIONS_PATH)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/diagnostics", dependencies=[Depends(require_token)])
async def diagnostics():
    health_body = await health()
    project = config.get_project()
    board_result = await arduino.board_list(json_format=True)
    devices = simplify_board_list(board_result.stdout) if board_result.exit_code == 0 else []
    checks = [
        {
            "id": "arduinoCli",
            "label": "Arduino CLI",
            "ok": bool(health_body["arduinoCliFound"]),
            "detail": health_body.get("arduinoCliPath") or "arduino-cli não encontrado no PATH",
        },
        {
            "id": "esp32Core",
            "label": "Pacote/core da placa",
            "ok": health_body.get("coreInstalled"),
            "detail": project.defaultFqbn,
        },
        _sketch_check(project),
        {
            "id": "serialMode",
            "label": "Monitor serial",
            "ok": True,
            "detail": "simulação/dev" if serial_manager.fake else "modo real",
        },
        {
            "id": "devices",
            "label": "Portas encontradas",
            "ok": len(devices) > 0,
            "detail": f"{len(devices)} porta(s) detectada(s)",
        },
    ]
    return {
        "ok": True,
        "health": health_body,
        "checks": checks,
        "boardChoices": {
            "devices": devices,
            "selectedPort": _selected_board_port(devices),
            "message": _board_choice_message(devices, board_result),
            "raw": result_to_dict(board_result, "board_list"),
        },
    }


@app.get("/api/templates", dependencies=[Depends(require_token)])
async def templates():
    return {"templates": template_catalog()}


@app.get("/api/templates/{template_id}", dependencies=[Depends(require_token)])
async def template_preview(template_id: str, projectId: str | None = None):
    try:
        project = config.get_project(projectId)
        return render_template(template_id, project_name=project.name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Template ou projeto não encontrado.") from exc


@app.post("/api/templates/{template_id}/create", dependencies=[Depends(require_token)])
async def template_create(template_id: str, req: TemplateCreateRequest):
    try:
        project = config.get_project(req.projectId)
        return create_template_file(template_id, project, confirmed=req.confirmed)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Template ou projeto não encontrado.") from exc
    except PolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/arduino/version", dependencies=[Depends(require_token)])
async def arduino_version():
    return result_to_dict(await arduino.version(), "version")


@app.get("/api/arduino/boards", dependencies=[Depends(require_token)])
async def arduino_boards():
    result = await arduino.board_list()
    return result_to_dict(result, "board_list")


@app.get("/api/arduino/board-choices", dependencies=[Depends(require_token)])
async def arduino_board_choices():
    result = await arduino.board_list(json_format=True)
    devices = simplify_board_list(result.stdout) if result.exit_code == 0 else []
    selected_port = _selected_board_port(devices)
    return {
        "ok": result.exit_code == 0,
        "devices": devices,
        "selectedPort": selected_port,
        "needsChoice": len(devices) > 1 or (len(devices) == 1 and not devices[0].get("isKnown")),
        "message": _board_choice_message(devices, result),
        "raw": result_to_dict(result, "board_list"),
    }


def _selected_board_port(devices):
    known_devices = [device for device in devices if device.get("isKnown")]
    if len(devices) == 1 and devices[0].get("isKnown"):
        return devices[0]["port"]
    if len(known_devices) == 1:
        return known_devices[0]["port"]
    return None


def _board_choice_message(devices, result):
    if result.exit_code != 0:
        return "Não consegui procurar a placa. Peça ajuda ao papai para conferir o Arduino CLI."
    if len(devices) == 0:
        return "Não achei nenhuma placa. Conecte o cabo USB e clique em procurar de novo."
    if len(devices) == 1:
        if devices[0].get("isKnown"):
            return f"Achei uma placa e já escolhi: {devices[0]['label']}."
        return f"Achei uma porta ({devices[0]['port']}), mas não tenho certeza se é a sua placa. Confira antes de enviar."
    known_devices = [device for device in devices if device.get("isKnown")]
    if len(known_devices) == 1:
        return f"Achei várias portas. A mais provável é {known_devices[0]['label']}; confira antes de enviar."
    return "Achei mais de uma placa. Escolha a que você quer usar."


@app.post("/api/arduino/compile", dependencies=[Depends(require_token)])
async def arduino_compile(req: CompileRequest):
    try:
        project = config.get_project(req.projectId)
        return result_to_dict(await arduino.compile(project, req.fqbn, req.sketchPath), "compile")
    except (PolicyError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/arduino/upload", dependencies=[Depends(require_token)])
async def arduino_upload(req: UploadRequest):
    try:
        project = config.get_project(req.projectId)
        return result_to_dict(
            await arduino.upload(project, req.port, req.confirmed, req.fqbn, req.sketchPath),
            "upload",
        )
    except (PolicyError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/serial/open", dependencies=[Depends(require_token)])
async def serial_open(req: SerialOpenRequest):
    try:
        session = serial_manager.open(req.port, req.baud)
    except PolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SerialError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": True,
        "sessionId": session.session_id,
        "port": session.port,
        "baud": session.baud,
        "fake": session.fake,
    }


@app.post("/api/serial/close", dependencies=[Depends(require_token)])
async def serial_close(req: SerialCloseRequest):
    return {"ok": serial_manager.close(req.sessionId)}


@app.post("/api/serial/clear", dependencies=[Depends(require_token)])
async def serial_clear(req: SerialCloseRequest):
    return {"ok": serial_manager.clear(req.sessionId)}


@app.post("/api/serial/write", dependencies=[Depends(require_token)])
async def serial_write(req: SerialWriteRequest):
    try:
        message = serial_manager.write(req.sessionId, req.text)
    except SerialError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "message": message}


@app.websocket("/api/serial/stream/{session_id}")
async def serial_stream(websocket: WebSocket, session_id: str):
    await websocket.accept()
    token = websocket.query_params.get("token")
    if not auth.check(token):
        await websocket.send_text(TOKEN_MISSING_MESSAGE)
        await websocket.close(code=1008)
        return
    if session_id not in serial_manager.sessions:
        await websocket.send_text("Sessão serial não encontrada. Abra o monitor de novo.")
        await websocket.close()
        return

    async def pump() -> None:
        async for line in serial_manager.stream(session_id):
            await websocket.send_text(line)

    async def watch_disconnect() -> None:
        # Detect the client closing the tab even when the board sends no data,
        # so a silent port does not leak an open serial session forever.
        try:
            while True:
                await websocket.receive()
        except WebSocketDisconnect:
            return

    pump_task = asyncio.ensure_future(pump())
    watch_task = asyncio.ensure_future(watch_disconnect())
    try:
        done, pending = await asyncio.wait(
            {pump_task, watch_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        for task in done:
            with suppress(Exception):
                task.result()
    finally:
        serial_manager.close(session_id)


@app.post("/api/chat", dependencies=[Depends(require_token)])
async def chat(req: ChatRequest):
    try:
        project = config.get_project(req.projectId)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail="Projeto não encontrado.") from exc

    context = {
        "project": {
            "id": project.id,
            "name": project.name,
            "sketch": project.sketch,
            "defaultFqbn": project.defaultFqbn,
        },
        **req.context,
    }
    reply = await hermes.send_message(req.message, context)
    return {
        "reply": reply.reply,
        "suggestedActions": reply.suggested_actions,
        "offline": reply.offline,
    }


@app.post("/api/chat/multimodal", dependencies=[Depends(require_token)])
async def chat_multimodal(req: ChatMultimodalRequest):
    try:
        project = config.get_project(req.projectId)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail="Projeto não encontrado.") from exc

    has_image = bool(req.imageDataUrl)
    if has_image:
        # Validate type/size up front; the bytes stay in memory and are never
        # written to disk or logged.
        try:
            parse_image_data_url(req.imageDataUrl)
        except ImageError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not (req.message.strip() or has_image):
        raise HTTPException(status_code=400, detail="Escreva uma mensagem ou anexe uma imagem.")

    context = {
        "project": {
            "id": project.id,
            "name": project.name,
            "sketch": project.sketch,
            "defaultFqbn": project.defaultFqbn,
        },
        **req.context,
    }
    reply = await vision.describe(req.message, req.imageDataUrl if has_image else None, context)
    return {
        "reply": reply.reply,
        "suggestedActions": reply.suggested_actions,
        "offline": reply.offline,
        "hasImage": has_image,
    }


# --- vibecoding: Davi edita o projeto por palavras, com saves no git ---------

def _code_agent_url() -> str | None:
    url = os.environ.get("ROTOM_DEX_CODE_URL")
    if url:
        return url
    base = os.environ.get("ROTOM_DEX_HERMES_URL")
    if not base:
        return None
    return (base[:-5] + "/code") if base.endswith("/chat") else (base.rstrip("/") + "/code")


async def _request_code_edits(instruction: str, current_code: str, filename: str) -> str:
    url = _code_agent_url()
    token = os.environ.get("ROTOM_DEX_HERMES_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    timeout = float(os.environ.get("ROTOM_DEX_CODE_TIMEOUT_SECONDS", "180"))
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            url,
            json={"instruction": instruction, "currentCode": current_code, "filename": filename},
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
    return data.get("edits", "") if isinstance(data, dict) else ""


def _vibe_save_message(instruction: str) -> str:
    return f"Davi pediu: {' '.join(instruction.split())[:72]}"


import re as _re

_SECRET_ASSIGN = _re.compile(r'(?i)\b(password|senha|secret|api[_]?key|token)(\s*=\s*")([^"]+)(")')


def _redact_secrets(code: str) -> str:
    """Hide secret values (Wi-Fi password, API keys) when showing code on screen."""
    return _SECRET_ASSIGN.sub(lambda m: f"{m.group(1)}{m.group(2)}••••••{m.group(4)}", code)


@app.get("/api/code/versions", dependencies=[Depends(require_token)])
async def code_versions(projectId: str | None = None):
    try:
        project = config.get_project(projectId)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail="Projeto não encontrado.") from exc
    return {"versions": codegen.list_versions(project.root)}


@app.get("/api/code/current", dependencies=[Depends(require_token)])
async def code_current(projectId: str | None = None):
    try:
        project = config.get_project(projectId)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail="Projeto não encontrado.") from exc
    try:
        sketch_path = Path(resolve_sketch_path(project))
    except PolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not sketch_path.exists():
        raise HTTPException(status_code=400, detail="Ainda não achei o arquivo do projeto.")
    content = sketch_path.read_text(encoding="utf-8", errors="replace")
    return {"filename": project.sketch, "content": _redact_secrets(content)}


@app.post("/api/code/restore", dependencies=[Depends(require_token)])
async def code_restore(req: CodeRestoreRequest):
    try:
        project = config.get_project(req.projectId)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail="Projeto não encontrado.") from exc
    if not req.confirmed:
        raise HTTPException(status_code=400, detail="Confirme para voltar a este save.")
    try:
        info = codegen.restore_version(project.root, req.hash)
    except CodegenError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": True,
        "message": f"Voltei para o save {info['restoredFrom']} ✅ Clique em 🧪 Testar ou 🚀 Enviar quando quiser.",
        **info,
    }


@app.post("/api/code/vibe", dependencies=[Depends(require_token)])
async def code_vibe(req: VibeRequest):
    try:
        project = config.get_project(req.projectId)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail="Projeto não encontrado.") from exc
    if not req.instruction.strip():
        raise HTTPException(status_code=400, detail="Escreva o que você quer criar ou mudar.")
    if _code_agent_url() is None:
        return {"ok": False, "offline": True, "message": "O cérebro de código do Rotom ainda não está ligado. Peça ajuda ao papai."}

    root = project.root
    try:
        sketch_path = Path(resolve_sketch_path(project))
    except PolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not sketch_path.exists():
        raise HTTPException(status_code=400, detail="Não achei o arquivo do projeto para mudar.")
    current_code = sketch_path.read_text(encoding="utf-8", errors="replace")

    codegen.ensure_repo(root)
    if not codegen.list_versions(root):
        codegen.commit_all(root, "Save inicial")

    try:
        edits_text = await _request_code_edits(req.instruction, current_code, project.sketch)
    except Exception:  # noqa: BLE001
        return {"ok": False, "offline": True, "message": "Não consegui falar com o cérebro de código agora. Tenta de novo daqui a pouco."}

    edits = codegen.parse_edits(edits_text or "")
    if not edits:
        return {"ok": False, "message": "Não consegui montar a mudança 🤔 Tenta explicar de outro jeito, com mais detalhes."}

    result = codegen.apply_edits(root, edits)
    if not result.applied:
        codegen.discard_changes(root)
        return {"ok": False, "message": "Tentei, mas não consegui encaixar a mudança no código. Tenta pedir de novo, mais simples.", "failed": result.failed}

    compiled = await arduino.compile(project)
    if compiled.exit_code == 0:
        save = codegen.commit_all(root, _vibe_save_message(req.instruction))
        return {
            "ok": True,
            "compileOk": True,
            "save": save,
            "applied": result.applied,
            "failed": result.failed,
            "message": "Pronto! Mudei, testei e salvei ✅ Agora clique em 🚀 Enviar pra colocar na placa.",
            "raw": result_to_dict(compiled, "compile"),
        }

    # The new code didn't compile. Decide if the change broke a working project,
    # or if the project simply can't be built in this environment (e.g. a library
    # the Davi has on his machine isn't installed here) — in which case we must
    # NOT punish the change: we still save it (versioned/recoverable) and say so.
    codegen.discard_changes(root)
    baseline = await arduino.compile(project)
    if baseline.exit_code == 0:
        return {
            "ok": False,
            "compileOk": False,
            "message": "Mudei, mas o código ficou com errinho — então voltei pro último save bom. " + friendly_arduino_message(compiled, "compile"),
            "failed": result.failed,
            "raw": result_to_dict(compiled, "compile"),
        }

    # Baseline também não compila aqui -> não dá pra usar a compilação como teste.
    codegen.apply_edits(root, edits)
    save = codegen.commit_all(root, _vibe_save_message(req.instruction) + " (nao testado aqui)")
    return {
        "ok": True,
        "compileOk": None,
        "save": save,
        "applied": result.applied,
        "failed": result.failed,
        "message": "Salvei a sua mudança ✅ — mas não consegui testar aqui (pode faltar uma biblioteca do projeto). Confira na sua máquina; se precisar, é só voltar para um save.",
        "raw": result_to_dict(compiled, "compile"),
    }
