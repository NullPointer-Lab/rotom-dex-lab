from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .arduino import ArduinoService
from .auth import TOKEN_MISSING_MESSAGE, SessionAuth
from .board_parser import simplify_board_list
from .config import load_config, load_missions
from .hermes_client import HermesClient
from .policy import PolicyError
from .serial_monitor import SerialError, SerialManager
from .translate import core_installed, friendly_arduino_message

ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "web"


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


class ChatRequest(BaseModel):
    message: str
    projectId: str | None = None
    context: dict[str, Any] = {}


def result_to_dict(result, action: str = "comando"):
    return {
        "args": result.args,
        "exitCode": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "ok": result.exit_code == 0,
        "message": friendly_arduino_message(result, action),
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
    return {"missions": load_missions()}


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
