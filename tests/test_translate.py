from bridge.runner import CommandResult
from bridge.translate import core_installed, friendly_arduino_message


def _result(exit_code, stderr="", stdout=""):
    return CommandResult(["arduino-cli"], exit_code, stdout, stderr)


def test_success_messages_per_action():
    assert "passou" in friendly_arduino_message(_result(0), "compile")
    assert "Enviei" in friendly_arduino_message(_result(0), "upload")


def test_cli_missing():
    msg = friendly_arduino_message(_result(127, "Executável não encontrado: arduino-cli"), "version")
    assert "Arduino CLI" in msg


def test_core_missing():
    msg = friendly_arduino_message(_result(1, "Error: platform not installed"), "compile")
    assert "ESP32" in msg or "core esp32" in msg


def test_invalid_fqbn():
    msg = friendly_arduino_message(_result(1, "invalid FQBN: bad:board"), "compile")
    assert "FQBN" in msg


def test_port_busy():
    msg = friendly_arduino_message(_result(1, "Error: Access is denied."), "upload")
    assert "ocupada" in msg or "bloqueada" in msg


def test_port_not_found():
    msg = friendly_arduino_message(_result(1, "Error: port not found"), "upload")
    assert "porta" in msg.lower()


def test_compile_error():
    msg = friendly_arduino_message(_result(1, "sketch.ino:5:3: error: expected ';'"), "compile")
    assert "errinho" in msg or "errin" in msg


def test_core_installed_detection():
    listing = "ID            Installed\nesp32:esp32   2.0.11"
    assert core_installed(listing, "esp32:esp32:esp32") is True
    assert core_installed(listing, "arduino:avr:uno") is False
