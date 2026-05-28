from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .arduino import ArduinoService
from .board_parser import simplify_board_list
from .config import load_config
from .hermes_client import HermesClient
from .policy import PolicyError
from .serial_monitor import SerialManager

ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "web"

app = FastAPI(title="Rotom Dex Lab", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(WEB_ROOT)), name="static")

config = load_config()
arduino = ArduinoService()
serial_manager = SerialManager()
hermes = HermesClient()


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


def result_to_dict(result):
    return {
        "args": result.args,
        "exitCode": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "ok": result.exit_code == 0,
    }


@app.get("/")
async def index():
    return FileResponse(WEB_ROOT / "index.html")


@app.get("/api/health")
async def health():
    found = arduino.runner.find_executable()
    return {
        "ok": True,
        "name": "Rotom Dex Lab",
        "bridgeVersion": "0.1.0",
        "arduinoCliFound": bool(found),
        "arduinoCliPath": found,
        "projects": [p.model_dump() for p in config.projects],
    }


@app.get("/api/arduino/version")
async def arduino_version():
    return result_to_dict(await arduino.version())


@app.get("/api/arduino/boards")
async def arduino_boards():
    result = await arduino.board_list()
    return result_to_dict(result)


@app.get("/api/arduino/board-choices")
async def arduino_board_choices():
    result = await arduino.board_list(json_format=True)
    devices = simplify_board_list(result.stdout) if result.exit_code == 0 else []
    return {
        "ok": result.exit_code == 0,
        "devices": devices,
        "selectedPort": devices[0]["port"] if len(devices) == 1 and devices[0].get("isKnown") else None,
        "needsChoice": len(devices) > 1 or (len(devices) == 1 and not devices[0].get("isKnown")),
        "message": _board_choice_message(devices, result),
        "raw": result_to_dict(result),
    }


def _board_choice_message(devices, result):
    if result.exit_code != 0:
        return "Não consegui procurar a placa. Peça ajuda ao papai para conferir o Arduino CLI."
    if len(devices) == 0:
        return "Não achei nenhuma placa. Conecte o cabo USB e clique em procurar de novo."
    if len(devices) == 1:
        if devices[0].get("isKnown"):
            return f"Achei uma placa e já escolhi: {devices[0]['label']}."
        return f"Achei uma porta ({devices[0]['port']}), mas não tenho certeza se é a sua placa. Confira antes de enviar."
    return "Achei mais de uma placa. Escolha a que você quer usar."


@app.post("/api/arduino/compile")
async def arduino_compile(req: CompileRequest):
    try:
        project = config.get_project(req.projectId)
        return result_to_dict(await arduino.compile(project, req.fqbn, req.sketchPath))
    except (PolicyError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/arduino/upload")
async def arduino_upload(req: UploadRequest):
    try:
        project = config.get_project(req.projectId)
        return result_to_dict(await arduino.upload(project, req.port, req.confirmed, req.fqbn, req.sketchPath))
    except (PolicyError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/serial/open")
async def serial_open(req: SerialOpenRequest):
    try:
        session = serial_manager.open(req.port, req.baud)
        return {"ok": True, "sessionId": session.session_id, "port": session.port, "baud": session.baud}
    except PolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/serial/close")
async def serial_close(req: SerialCloseRequest):
    return {"ok": serial_manager.close(req.sessionId)}


@app.websocket("/api/serial/stream/{session_id}")
async def serial_stream(websocket: WebSocket, session_id: str):
    await websocket.accept()
    if session_id not in serial_manager.sessions:
        await websocket.send_text("Sessão serial não encontrada.")
        await websocket.close()
        return
    try:
        async for line in serial_manager.fake_stream(session_id):
            await websocket.send_text(line)
    except WebSocketDisconnect:
        serial_manager.close(session_id)


@app.post("/api/chat")
async def chat(req: ChatRequest):
    try:
        project = config.get_project(req.projectId).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=400, detail="Projeto não encontrado.") from exc
    reply = await hermes.send_message(req.message, {"project": project, **req.context})
    return {"reply": reply.reply, "suggestedActions": reply.suggested_actions}
