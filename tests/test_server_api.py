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
