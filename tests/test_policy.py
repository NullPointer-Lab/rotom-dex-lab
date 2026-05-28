import pytest

from bridge.config import ProjectConfig
from bridge.policy import PolicyError, resolve_sketch_path, validate_fqbn, validate_port


@pytest.fixture
def project():
    return ProjectConfig(
        id="davibot",
        name="DaviBot",
        root="C:/Users/Davi/Documents/DaviBot",
        sketch="DaviBot.ino",
        allowedFqbns=["esp32:esp32:esp32"],
        defaultFqbn="esp32:esp32:esp32",
    )


def test_validate_port_accepts_com_port():
    assert validate_port(" com5 ") == "COM5"


@pytest.mark.parametrize("port", ["/dev/ttyUSB0", "COM0", "COM999", "COMX", "COM5 & del *"])
def test_validate_port_rejects_invalid(port):
    with pytest.raises(PolicyError):
        validate_port(port)


def test_validate_fqbn_allowlist(project):
    assert validate_fqbn(project, None) == "esp32:esp32:esp32"
    with pytest.raises(PolicyError):
        validate_fqbn(project, "arduino:avr:uno")


def test_resolve_sketch_path_within_windows_root(project):
    path = resolve_sketch_path(project, "src/DaviBot.ino")
    assert "DaviBot" in path
    assert path.endswith("src\\DaviBot.ino") or path.endswith("src/DaviBot.ino")


@pytest.mark.parametrize("sketch", ["../secrets.ino", "C:/Users/Davi/Documents/Other/Other.ino"])
def test_resolve_sketch_path_rejects_escape(project, sketch):
    with pytest.raises(PolicyError):
        resolve_sketch_path(project, sketch)
