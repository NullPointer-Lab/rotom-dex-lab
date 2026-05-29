import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bridge import server
from bridge.board_parser import simplify_board_list
from bridge.config import AppConfig, ProjectConfig, load_missions, save_mission_status
from bridge.serial_monitor import SerialManager
from bridge.sketch_templates import create_template_file, render_template, template_catalog
from bridge.policy import PolicyError


class MemorySerial:
    def __init__(self, port, baudrate, timeout):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.writes = []
        self.closed = False

    def readline(self):
        return b""

    def write(self, data):
        self.writes.append(data)
        return len(data)

    def close(self):
        self.closed = True


def test_detected_ports_include_reason_and_confidence_for_ch340():
    stdout = json.dumps(
        {
            "detected_ports": [
                {"port": {"address": "COM5", "protocol_label": "Serial Port", "properties": {}}},
                {
                    "port": {
                        "address": "COM9",
                        "protocol_label": "Serial Port (USB)",
                        "properties": {"vid": "0x1A86", "pid": "0x7523"},
                    }
                },
            ]
        }
    )
    devices = simplify_board_list(stdout)
    assert devices[0]["port"] == "COM9"
    assert devices[0]["confidence"] == "provavel"
    assert "VID 0x1A86 / PID 0x7523" in devices[0]["reason"]
    assert devices[1]["confidence"] == "generica"


def test_detected_ports_without_matching_boards_still_show_all_serial_ports():
    stdout = json.dumps(
        {
            "detected_ports": [
                {"port": {"address": "COM5", "label": "COM5", "protocol_label": "Serial Port", "properties": {}}},
                {"port": {"address": "COM6", "label": "COM6", "protocol_label": "Serial Port", "properties": {}}},
                {"port": {"address": "COM3", "label": "COM3", "protocol_label": "Serial Port", "properties": {}}},
                {"port": {"address": "COM7", "label": "COM7", "protocol_label": "Serial Port", "properties": {}}},
                {"port": {"address": "COM8", "label": "COM8", "protocol_label": "Serial Port", "properties": {}}},
                {"port": {"address": "COM4", "label": "COM4", "protocol_label": "Serial Port", "properties": {}}},
                {
                    "port": {
                        "address": "COM9",
                        "label": "COM9",
                        "protocol_label": "Serial Port (USB)",
                        "properties": {"pid": "0x7523", "serialNumber": "", "vid": "0x1A86"},
                    }
                },
            ]
        }
    )
    devices = simplify_board_list(stdout)
    assert [device["port"] for device in devices] == ["COM9", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8"]
    assert devices[0]["isKnown"] is True
    assert devices[0]["name"].startswith("USB-Serial CH340")


def test_mission_status_can_be_saved(tmp_path):
    path = tmp_path / "missions.json"
    path.write_text(
        json.dumps({"version": 1, "missions": [{"id": "motor", "title": "Motor", "status": "todo"}]}),
        encoding="utf-8",
    )
    updated = save_mission_status("motor", "doing", path)
    assert updated[0]["status"] == "doing"
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["version"] == 1
    assert load_missions(path)[0]["status"] == "doing"


def test_mission_status_rejects_invalid_status_and_unknown_id(tmp_path):
    path = tmp_path / "missions.json"
    path.write_text(json.dumps({"missions": [{"id": "motor", "title": "Motor", "status": "todo"}]}), encoding="utf-8")
    with pytest.raises(ValueError):
        save_mission_status("motor", "finished", path)
    with pytest.raises(KeyError):
        save_mission_status("missing", "done", path)


def test_serial_manager_can_write_text_and_clear_recent_lines():
    mgr = SerialManager(serial_factory=MemorySerial, fake=False)
    session = mgr.open("COM5", 115200)
    session.lines.extend(["a", "b"])
    assert mgr.write(session.session_id, "LED ON") == "Enviei para a placa: LED ON"
    assert session.serial.writes == [b"LED ON\n"]
    assert mgr.clear(session.session_id) is True
    assert session.lines == []


def test_serial_manager_rejects_unsafe_writes_and_missing_sessions():
    mgr = SerialManager(serial_factory=MemorySerial, fake=False)
    session = mgr.open("COM5", 115200)
    with pytest.raises(Exception, match="Digite uma mensagem"):
        mgr.write(session.session_id, "   ")
    with pytest.raises(Exception, match="muito grande"):
        mgr.write(session.session_id, "x" * 201)
    mgr.close(session.session_id)
    with pytest.raises(Exception, match="não está aberto"):
        mgr.write(session.session_id, "ping")
    assert mgr.clear("missing") is False


def test_template_catalog_and_render_are_child_safe():
    catalog = template_catalog()
    assert any(item["id"] == "motor-test" for item in catalog)
    rendered = render_template("motor-test", project_name="DaviBot")
    assert "void setup()" in rendered["content"]
    assert rendered["filename"].endswith(".ino")
    assert "motor" in rendered["description"].lower()


def test_template_create_rejects_windows_path_on_non_windows(monkeypatch):
    monkeypatch.setattr("bridge.sketch_templates.os.name", "posix")
    project = ProjectConfig(
        id="davibot",
        name="DaviBot",
        root="C:/Users/Davi/Documents/DaviBot",
        sketch="DaviBot.ino",
        allowedFqbns=["esp32:esp32:esp32"],
        defaultFqbn="esp32:esp32:esp32",
    )
    with pytest.raises(PolicyError, match="caminho Windows"):
        create_template_file("motor-test", project, confirmed=True)
    assert not (Path.cwd() / "C:").exists()


def test_template_create_requires_confirmation_and_rejects_duplicate(tmp_path):
    project = ProjectConfig(
        id="davibot",
        name="DaviBot",
        root=str(tmp_path),
        sketch="DaviBot.ino",
        allowedFqbns=["esp32:esp32:esp32"],
        defaultFqbn="esp32:esp32:esp32",
    )
    with pytest.raises(PolicyError, match="Confirme"):
        create_template_file("motor-test", project, confirmed=False)
    first = create_template_file("motor-test", project, confirmed=True)
    assert Path(first["path"]).exists()
    with pytest.raises(PolicyError, match="já existe"):
        create_template_file("motor-test", project, confirmed=True)


def test_diagnostics_reports_windows_sketch_path_without_posix_existence_check(monkeypatch):
    monkeypatch.setattr(server.os, "name", "posix")
    project = ProjectConfig(
        id="davibot",
        name="DaviBot",
        root="C:/Users/Davi/Documents/DaviBot",
        sketch="DaviBot.ino",
        allowedFqbns=["esp32:esp32:esp32"],
        defaultFqbn="esp32:esp32:esp32",
    )
    check = server._sketch_check(project)
    assert check["ok"] is None
    assert "caminho Windows" in check["detail"]
    assert "C:" in check["detail"]


def test_api_diagnostics_mission_update_serial_write_and_template_preview(monkeypatch, tmp_path):
    client = TestClient(server.app)
    token = server.auth.token

    missions_path = tmp_path / "missions.json"
    missions_path.write_text(json.dumps({"missions": [{"id": "motor", "title": "Motor", "status": "todo"}]}), encoding="utf-8")
    monkeypatch.setattr(server, "MISSIONS_PATH", missions_path)

    project_root = tmp_path / "DaviBot"
    project_root.mkdir()
    fake_config = AppConfig(
        defaultProjectId="davibot",
        projects=[
            ProjectConfig(
                id="davibot",
                name="DaviBot",
                root=str(project_root),
                sketch="DaviBot.ino",
                allowedFqbns=["esp32:esp32:esp32"],
                defaultFqbn="esp32:esp32:esp32",
            )
        ],
    )
    monkeypatch.setattr(server, "config", fake_config)
    monkeypatch.setattr(server, "serial_manager", SerialManager(serial_factory=MemorySerial, fake=False))

    diag = client.get("/api/diagnostics", headers={"X-Rotom-Token": token}).json()
    assert diag["ok"] is True
    assert "checks" in diag
    assert any(check["id"] == "sketchPath" for check in diag["checks"])

    mission = client.post(
        "/api/missions/motor/status",
        headers={"X-Rotom-Token": token},
        json={"status": "done"},
    )
    assert mission.status_code == 200
    assert mission.json()["missions"][0]["status"] == "done"

    session = client.post(
        "/api/serial/open",
        headers={"X-Rotom-Token": token},
        json={"port": "COM5", "baud": 115200},
    ).json()
    sent = client.post(
        "/api/serial/write",
        headers={"X-Rotom-Token": token},
        json={"sessionId": session["sessionId"], "text": "ping"},
    )
    assert sent.status_code == 200
    assert sent.json()["message"] == "Enviei para a placa: ping"

    preview = client.get("/api/templates/motor-test", headers={"X-Rotom-Token": token})
    assert preview.status_code == 200
    assert "void loop()" in preview.json()["content"]

    created = client.post(
        "/api/templates/motor-test/create",
        headers={"X-Rotom-Token": token},
        json={"confirmed": True},
    )
    assert created.status_code == 200
    assert Path(created.json()["path"]).exists()
