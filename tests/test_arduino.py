import pytest

from bridge.arduino import ArduinoService
from bridge.config import ProjectConfig
from bridge.runner import CommandResult


class FakeRunner:
    def __init__(self):
        self.calls = []

    async def run(self, args, timeout_seconds=None):
        self.calls.append((list(args), timeout_seconds))
        return CommandResult(["arduino-cli", *args], 0, "ok", "")


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


@pytest.mark.asyncio
async def test_compile_uses_argument_list_without_shell(project):
    runner = FakeRunner()
    service = ArduinoService(runner)
    result = await service.compile(project)
    assert result.ok if hasattr(result, "ok") else result.exit_code == 0
    args, timeout = runner.calls[0]
    assert args[:3] == ["compile", "--fqbn", "esp32:esp32:esp32"]
    assert timeout == 180


@pytest.mark.asyncio
async def test_upload_requires_confirmation(project):
    service = ArduinoService(FakeRunner())
    result = await service.upload(project, port="COM5", confirmed=False)
    assert result.exit_code == 2
    assert "confirma" in result.stderr.lower()


@pytest.mark.asyncio
async def test_upload_validated_call(project):
    runner = FakeRunner()
    service = ArduinoService(runner)
    await service.upload(project, port="com5", confirmed=True)
    args, _ = runner.calls[0]
    assert args[:5] == ["upload", "-p", "COM5", "--fqbn", "esp32:esp32:esp32"]
