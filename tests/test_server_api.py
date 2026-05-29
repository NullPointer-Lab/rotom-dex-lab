import json

import pytest
from fastapi.testclient import TestClient

from bridge import server
from bridge.auth import TOKEN_MISSING_MESSAGE
from bridge.hermes_client import HermesReply
from bridge.runner import CommandResult
from bridge.server import startup_banner


@pytest.fixture
def client():
    return TestClient(server.app)


@pytest.fixture
def token():
    return server.auth.token


# --- token gating -----------------------------------------------------------

def test_health_is_open_without_token(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert "fakeSerial" in body
    assert "hermesConfigured" in body


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("get", "/api/missions", None),
        ("post", "/api/missions/rtc/status", {"status": "done"}),
        ("get", "/api/diagnostics", None),
        ("get", "/api/templates", None),
        ("get", "/api/templates/motor-test", None),
        ("post", "/api/templates/motor-test/create", {"confirmed": True}),
        ("get", "/api/arduino/board-choices", None),
        ("post", "/api/arduino/compile", {}),
        ("post", "/api/arduino/upload", {"port": "COM5", "confirmed": True}),
        ("post", "/api/serial/open", {"port": "COM5", "baud": 115200}),
        ("post", "/api/serial/clear", {"sessionId": "serial-COM5-115200"}),
        ("post", "/api/serial/write", {"sessionId": "serial-COM5-115200", "text": "ping"}),
        ("post", "/api/chat", {"message": "oi"}),
        ("post", "/api/chat/multimodal", {"message": "oi"}),
        ("post", "/api/code/vibe", {"instruction": "muda"}),
        ("get", "/api/code/versions", None),
        ("get", "/api/code/current", None),
        ("post", "/api/code/restore", {"hash": "abc1234", "confirmed": True}),
    ],
)
def test_action_endpoints_reject_missing_token(client, method, path, payload):
    kwargs = {"json": payload} if payload is not None else {}
    res = getattr(client, method)(path, **kwargs)
    assert res.status_code == 401
    assert res.json()["detail"] == TOKEN_MISSING_MESSAGE


def test_action_endpoint_rejects_wrong_token(client):
    res = client.get("/api/missions", headers={"X-Rotom-Token": "errado"})
    assert res.status_code == 401


def test_missions_with_header_token(client, token):
    res = client.get("/api/missions", headers={"X-Rotom-Token": token})
    assert res.status_code == 200
    assert isinstance(res.json()["missions"], list)


def test_token_accepted_as_query_param(client, token):
    res = client.get(f"/api/missions?token={token}")
    assert res.status_code == 200


# --- board detection endpoint (regression for the "devices: []" bug) --------

# Exact arduino-cli output seen on Isaac's machine: detected_ports with NO
# matching_boards. COM9 is a CH340 (vid 0x1A86 / pid 0x7523). The endpoint must
# never collapse this into devices: [] / "Não achei nenhuma placa".
BUG_BOARD_LIST_JSON = json.dumps(
    {
        "detected_ports": [
            {
                "port": {
                    "address": p,
                    "label": p,
                    "protocol": "serial",
                    "protocol_label": "Serial Port",
                    "properties": {},
                }
            }
            for p in ("COM5", "COM6", "COM3", "COM7", "COM8", "COM4")
        ]
        + [
            {
                "port": {
                    "address": "COM9",
                    "label": "COM9",
                    "protocol": "serial",
                    "protocol_label": "Serial Port (USB)",
                    "properties": {"pid": "0x7523", "serialNumber": "", "vid": "0x1A86"},
                }
            }
        ]
    }
)


def test_board_choices_never_empty_when_ports_detected(client, token, monkeypatch):
    async def fake_board_list(json_format=False):
        return CommandResult(
            args=["arduino-cli", "board", "list", "--format", "json"],
            exit_code=0,
            stdout=BUG_BOARD_LIST_JSON,
            stderr="",
        )

    monkeypatch.setattr(server.arduino, "board_list", fake_board_list)
    res = client.get("/api/arduino/board-choices", headers={"X-Rotom-Token": token})
    assert res.status_code == 200
    body = res.json()

    # detected_ports com portas NUNCA pode virar devices vazio.
    assert body["devices"], "detected_ports tinha portas mas devices veio vazio"
    ports = {device["port"] for device in body["devices"]}
    assert ports == {"COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9"}

    # COM9 (CH340) é a mais provável: sugerida e em primeiro.
    assert body["devices"][0]["port"] == "COM9"
    assert body["devices"][0]["isKnown"] is True
    assert body["selectedPort"] == "COM9"
    assert body["needsChoice"] is True

    # Mensagem amigável aponta COM9 e nunca diz que não achou nada.
    assert "COM9" in body["message"]
    assert "Não achei nenhuma placa" not in body["message"]


# --- multimodal chat endpoint (image paste) ---------------------------------

PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


def test_multimodal_offline_reply_with_image(client, token):
    res = client.post(
        "/api/chat/multimodal",
        headers={"X-Rotom-Token": token},
        json={"message": "o que é isso?", "imageDataUrl": PNG_DATA_URL},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["hasImage"] is True
    assert body["offline"] is True  # nenhum provedor de visão configurado por padrão
    assert body["reply"]
    # nunca executa ação sozinho: o endpoint só sugere botões seguros.
    for action in body["suggestedActions"]:
        assert action["type"] in {
            "arduino.board_list",
            "arduino.compile",
            "arduino.upload",
            "serial.open",
            "diagnostics.open",
            "templates.list",
        }


def test_multimodal_rejects_invalid_image(client, token):
    res = client.post(
        "/api/chat/multimodal",
        headers={"X-Rotom-Token": token},
        json={"message": "olha", "imageDataUrl": "data:application/pdf;base64,aGk="},
    )
    assert res.status_code == 400


def test_multimodal_requires_message_or_image(client, token):
    res = client.post(
        "/api/chat/multimodal",
        headers={"X-Rotom-Token": token},
        json={"message": "   "},
    )
    assert res.status_code == 400


# --- vibecoding (git-backed code edits) -------------------------------------

class _FakeConfig:
    def __init__(self, project):
        self._project = project

    def get_project(self, project_id=None):
        return self._project


def _vibe_project(tmp_path):
    from bridge.config import ProjectConfig

    sketch = tmp_path / "ZappRobotFinal.ino"
    sketch.write_text('void setup(){}\nString nome = "Davi";\n', encoding="utf-8")
    project = ProjectConfig(
        id="davibot",
        name="Zapp",
        root=str(tmp_path),
        sketch="ZappRobotFinal.ino",
        allowedFqbns=["esp32:esp32:esp32"],
        defaultFqbn="esp32:esp32:esp32",
    )
    return project, sketch


VIBE_EDIT = (
    "ARQUIVO: ZappRobotFinal.ino\n"
    "<<<<<<< BUSCAR\n"
    'String nome = "Davi";\n'
    "=======\n"
    'String nome = "Davizinho";\n'
    ">>>>>>> SUBSTITUIR\n"
)


def test_vibe_applies_edit_commits_and_compiles(client, token, tmp_path, monkeypatch):
    from bridge import codegen
    from bridge.runner import CommandResult

    project, sketch = _vibe_project(tmp_path)
    monkeypatch.setattr(server, "config", _FakeConfig(project))
    monkeypatch.setenv("ROTOM_DEX_HERMES_URL", "http://agent.test/chat")

    async def fake_edits(instruction, current_code, filename):
        assert 'String nome = "Davi";' in current_code
        return VIBE_EDIT

    async def fake_compile(proj, fqbn=None, sketch_path=None):
        return CommandResult(args=["arduino-cli", "compile"], exit_code=0, stdout="ok", stderr="")

    async def no_port():
        return None

    monkeypatch.setattr(server, "_request_code_edits", fake_edits)
    monkeypatch.setattr(server.arduino, "compile", fake_compile)
    monkeypatch.setattr(server, "_detect_board_port", no_port)  # no board -> skip auto-upload

    res = client.post("/api/code/vibe", headers={"X-Rotom-Token": token}, json={"instruction": "muda o nome para Davizinho"})
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True and body["compileOk"] is True and body["save"]
    assert 'Davizinho' in sketch.read_text(encoding="utf-8")
    assert codegen.list_versions(str(tmp_path))  # a save was recorded


def test_vibe_auto_uploads_after_compile(client, token, tmp_path, monkeypatch):
    from bridge.runner import CommandResult

    project, sketch = _vibe_project(tmp_path)
    monkeypatch.setattr(server, "config", _FakeConfig(project))
    monkeypatch.setenv("ROTOM_DEX_HERMES_URL", "http://agent.test/chat")
    captured = {}

    async def fake_edits(instruction, current_code, filename):
        return VIBE_EDIT

    async def fake_compile(proj, fqbn=None, sketch_path=None):
        return CommandResult(["c"], 0, "ok", "")

    async def fake_detect():
        return "COM9"

    async def fake_upload(proj, port, confirmed, fqbn=None, sketch_path=None):
        captured["port"] = port
        captured["confirmed"] = confirmed
        return CommandResult(["u"], 0, "Uploaded", "")

    monkeypatch.setattr(server, "_request_code_edits", fake_edits)
    monkeypatch.setattr(server.arduino, "compile", fake_compile)
    monkeypatch.setattr(server, "_detect_board_port", fake_detect)
    monkeypatch.setattr(server.arduino, "upload", fake_upload)

    res = client.post("/api/code/vibe", headers={"X-Rotom-Token": token}, json={"instruction": "muda"})
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["upload"] and body["upload"]["ok"] is True and body["upload"]["port"] == "COM9"
    assert captured == {"port": "COM9", "confirmed": True}  # uploaded automatically
    assert "enviei" in body["message"].lower()


def test_vibe_reverts_when_change_breaks_a_working_build(client, token, tmp_path, monkeypatch):
    from bridge.runner import CommandResult

    project, sketch = _vibe_project(tmp_path)
    monkeypatch.setattr(server, "config", _FakeConfig(project))
    monkeypatch.setenv("ROTOM_DEX_HERMES_URL", "http://agent.test/chat")

    async def fake_edits(instruction, current_code, filename):
        return VIBE_EDIT

    # Baseline compiles; only the changed code (with "Davizinho") "breaks".
    async def fake_compile(proj, fqbn=None, sketch_path=None):
        broken = "Davizinho" in sketch.read_text(encoding="utf-8")
        return CommandResult(args=["c"], exit_code=1 if broken else 0, stdout="", stderr="boom" if broken else "")

    monkeypatch.setattr(server, "_request_code_edits", fake_edits)
    monkeypatch.setattr(server.arduino, "compile", fake_compile)

    res = client.post("/api/code/vibe", headers={"X-Rotom-Token": token}, json={"instruction": "muda o nome"})
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False and body.get("compileOk") is False
    # bad change rolled back to the last good save
    assert "Davizinho" not in sketch.read_text(encoding="utf-8")
    assert "Davi" in sketch.read_text(encoding="utf-8")


def test_vibe_saves_anyway_when_project_cannot_build_here(client, token, tmp_path, monkeypatch):
    from bridge import codegen
    from bridge.runner import CommandResult

    project, sketch = _vibe_project(tmp_path)
    monkeypatch.setattr(server, "config", _FakeConfig(project))
    monkeypatch.setenv("ROTOM_DEX_HERMES_URL", "http://agent.test/chat")

    async def fake_edits(instruction, current_code, filename):
        return VIBE_EDIT

    # Nothing compiles here (e.g. a missing library) — baseline fails too.
    async def fake_compile(proj, fqbn=None, sketch_path=None):
        return CommandResult(args=["c"], exit_code=1, stdout="", stderr="fatal error: Lib.h: No such file")

    async def fake_search(query):
        return CommandResult(args=["s"], exit_code=0, stdout='{"libraries":[]}', stderr="")

    monkeypatch.setattr(server, "_request_code_edits", fake_edits)
    monkeypatch.setattr(server.arduino, "compile", fake_compile)
    monkeypatch.setattr(server.arduino, "lib_search", fake_search)  # auto-heal finds nothing -> stays offline

    res = client.post("/api/code/vibe", headers={"X-Rotom-Token": token}, json={"instruction": "muda o nome"})
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True and body.get("compileOk") is None and body["save"]
    # change is kept and versioned despite no compile gate
    assert "Davizinho" in sketch.read_text(encoding="utf-8")
    assert codegen.list_versions(str(tmp_path))


class _FakeArduinoAutoheal:
    """Compile fails once (missing Foo.h), then succeeds after a lib install."""

    def __init__(self):
        self.compiles = 0
        self.installed = []

    async def compile(self, project, fqbn=None, sketch_path=None):
        from bridge.runner import CommandResult

        self.compiles += 1
        if self.compiles == 1:
            return CommandResult(["c"], 1, "", "fatal error: Foo.h: No such file or directory")
        return CommandResult(["c"], 0, "ok", "")

    async def lib_search(self, query):
        from bridge.runner import CommandResult

        return CommandResult(["s"], 0, '{"libraries":[{"name":"Foo Lib","provides_includes":["Foo.h"]}]}', "")

    async def lib_install(self, name):
        from bridge.runner import CommandResult

        self.installed.append(name)
        return CommandResult(["i"], 0, f"Installed {name}", "")


def test_compile_autoheals_missing_library(client, token, monkeypatch):
    from bridge.config import ProjectConfig

    project = ProjectConfig(
        id="davibot", name="Zapp", root="C:/tmp/zapp", sketch="x.ino",
        allowedFqbns=["esp32:esp32:esp32"], defaultFqbn="esp32:esp32:esp32",
    )
    monkeypatch.setattr(server, "config", _FakeConfig(project))
    monkeypatch.setattr(server, "arduino", _FakeArduinoAutoheal())
    res = client.post("/api/arduino/compile", headers={"X-Rotom-Token": token}, json={})
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body.get("installedLibraries") == ["Foo Lib"]
    assert "Foo Lib" in body["message"]


def test_code_current_redacts_secrets(client, token, tmp_path, monkeypatch):
    project, sketch = _vibe_project(tmp_path)
    sketch.write_text(
        'const char* ssid = "familia-leal";\nconst char* password = "supersecreta123";\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(server, "config", _FakeConfig(project))
    res = client.get("/api/code/current", headers={"X-Rotom-Token": token})
    assert res.status_code == 200
    content = res.json()["content"]
    assert "supersecreta123" not in content  # password hidden
    assert "••••••" in content
    assert "familia-leal" in content  # SSID (network name) still shown


# --- chat context enrichment (Phase 2) --------------------------------------

class RecordingHermes:
    configured = True

    def __init__(self):
        self.last_context = None

    async def send_message(self, message, context):
        self.last_context = context
        return HermesReply(reply="ok", suggested_actions=[], offline=False)


def test_chat_enriches_context_with_project_and_frontend_state(client, token, monkeypatch):
    fake = RecordingHermes()
    monkeypatch.setattr(server, "hermes", fake)
    res = client.post(
        "/api/chat",
        headers={"X-Rotom-Token": token},
        json={
            "message": "o que deu errado?",
            "context": {"selectedPort": "COM5", "lastResult": {"action": "compile", "ok": False}},
        },
    )
    assert res.status_code == 200
    ctx = fake.last_context
    assert ctx["project"]["defaultFqbn"] == "esp32:esp32:esp32"
    assert ctx["selectedPort"] == "COM5"
    assert ctx["lastResult"]["ok"] is False


def test_chat_offline_when_hermes_unconfigured(client, token, monkeypatch):
    from bridge.hermes_client import HermesClient

    monkeypatch.setattr(server, "hermes", HermesClient(url=None))
    res = client.post(
        "/api/chat",
        headers={"X-Rotom-Token": token},
        json={"message": "quero compilar"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["offline"] is True
    assert any(a["type"] == "arduino.compile" for a in body["suggestedActions"])


def test_chat_routes_code_change_to_vibe(client, token, monkeypatch):
    from bridge.hermes_client import HermesReply

    class _CodeHermes:
        configured = True

        async def send_message(self, message, context):
            return HermesReply(reply="CODE: deixa o relogio vermelho", suggested_actions=[], offline=False)

    seen = {}

    async def fake_run_vibe(project, instruction, port=None):
        seen["instruction"] = instruction
        seen["port"] = port
        return {"ok": True, "message": "Pronto! Programei e já enviei 🚀✅", "upload": {"ok": True, "port": "COM9"}}

    monkeypatch.setattr(server, "hermes", _CodeHermes())
    monkeypatch.setattr(server, "_run_vibe", fake_run_vibe)
    res = client.post(
        "/api/chat",
        headers={"X-Rotom-Token": token},
        json={"message": "deixa o relogio vermelho", "context": {"selectedPort": "COM9"}},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["codeChange"] is True
    assert "enviei" in body["reply"].lower()
    assert seen == {"instruction": "deixa o relogio vermelho", "port": "COM9"}


def test_chat_normal_message_does_not_touch_code(client, token, monkeypatch):
    from bridge.hermes_client import HermesReply

    class _ChatHermes:
        configured = True

        async def send_message(self, message, context):
            return HermesReply(reply="Oi, Davi! Como posso ajudar?", suggested_actions=[], offline=False)

    called = {"vibe": False}

    async def fake_run_vibe(project, instruction, port=None):
        called["vibe"] = True
        return {"ok": True}

    monkeypatch.setattr(server, "hermes", _ChatHermes())
    monkeypatch.setattr(server, "_run_vibe", fake_run_vibe)
    res = client.post("/api/chat", headers={"X-Rotom-Token": token}, json={"message": "oi"})
    assert res.status_code == 200
    body = res.json()
    assert body.get("codeChange") is not True
    assert "Oi, Davi" in body["reply"]
    assert called["vibe"] is False


# --- websocket token gating -------------------------------------------------

def test_serial_websocket_rejects_bad_token(client):
    with client.websocket_connect("/api/serial/stream/whatever?token=errado") as ws:
        assert ws.receive_text() == TOKEN_MISSING_MESSAGE


def test_serial_websocket_unknown_session_message(client, token):
    with client.websocket_connect(f"/api/serial/stream/nada?token={token}") as ws:
        assert "não encontrada" in ws.receive_text()


def test_fake_serial_streams_labeled_simulation_and_cleans_up(client, token, monkeypatch):
    import time

    from bridge.serial_monitor import SerialManager

    fake_mgr = SerialManager(fake=True)
    monkeypatch.setattr(server, "serial_manager", fake_mgr)
    session = fake_mgr.open("COM5", 115200)
    assert session.fake is True

    with client.websocket_connect(
        f"/api/serial/stream/{session.session_id}?token={token}"
    ) as ws:
        line = ws.receive_text()
    assert "SIMULAÇÃO" in line

    # Client disconnected: the session must be closed even though the (simulated)
    # stream was mid-sleep and sent no further data.
    for _ in range(100):
        if session.session_id not in fake_mgr.sessions:
            break
        time.sleep(0.02)
    assert session.session_id not in fake_mgr.sessions


# --- startup banner ---------------------------------------------------------

def test_startup_banner_includes_url_token_and_status():
    lines = startup_banner(
        token="abc123",
        port=8765,
        hermes_configured=False,
        arduino_found=False,
        fake_serial=False,
    )
    text = "\n".join(lines)
    assert "http://127.0.0.1:8765/?token=abc123" in text
    assert "abc123" in text
    assert "offline" in text  # hermes not configured
    assert "NAO encontrado" in text  # arduino missing
    assert "SIMULACAO" not in text  # fake serial off


def test_startup_banner_flags_fake_serial():
    lines = startup_banner(
        token="t",
        port="9000",
        hermes_configured=True,
        arduino_found=True,
        fake_serial=True,
    )
    text = "\n".join(lines)
    assert "SIMULACAO" in text
    assert "configurado" in text
