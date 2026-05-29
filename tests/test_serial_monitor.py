import pytest

from bridge.policy import PolicyError
from bridge.serial_monitor import SerialError, SerialManager


def test_close_port_frees_sessions_for_upload():
    mgr = SerialManager(fake=True)
    mgr.open("COM9", 115200)
    assert mgr.close_port("com9") is True  # case-insensitive, closes the open session
    assert mgr.sessions == {}
    assert mgr.close_port("COM9") is False  # nothing left to close


class FakeSerial:
    """Stand-in for serial.Serial; never touches real hardware."""

    instances = []

    def __init__(self, port, baudrate, timeout):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.closed = False
        self._lines = [b"ola\r\n", b"mundo\n", b""]
        self._i = 0
        FakeSerial.instances.append(self)

    def readline(self):
        if self._i < len(self._lines):
            line = self._lines[self._i]
            self._i += 1
            return line
        return b""

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _reset_instances():
    FakeSerial.instances = []


# --- fake-mode flag is opt-in only ------------------------------------------

def test_fake_mode_off_by_default(monkeypatch):
    monkeypatch.delenv("ROTOM_DEX_FAKE_SERIAL", raising=False)
    assert SerialManager().fake is False


def test_fake_mode_on_with_env_flag(monkeypatch):
    monkeypatch.setenv("ROTOM_DEX_FAKE_SERIAL", "1")
    assert SerialManager().fake is True


# --- real mode uses a real serial object ------------------------------------

def test_open_uses_serial_factory_in_real_mode():
    mgr = SerialManager(serial_factory=FakeSerial, fake=False)
    session = mgr.open("com5", 115200)
    assert session.fake is False
    assert isinstance(session.serial, FakeSerial)
    assert session.port == "COM5"
    assert session.serial.baudrate == 115200


@pytest.mark.asyncio
async def test_real_stream_reads_lines_then_close_closes_port():
    mgr = SerialManager(serial_factory=FakeSerial, fake=False)
    session = mgr.open("COM5", 115200)
    lines = []
    async for line in mgr.stream(session.session_id):
        lines.append(line)
        if len(lines) == 2:
            break
    assert lines == ["ola", "mundo"]
    assert mgr.close(session.session_id) is True
    assert session.serial.closed is True
    assert session.session_id not in mgr.sessions


@pytest.mark.asyncio
async def test_real_stream_reports_lost_connection_in_ptbr():
    class Flaky:
        def readline(self):
            raise OSError("device disconnected")

        def close(self):
            pass

    mgr = SerialManager(serial_factory=lambda **kwargs: Flaky(), fake=False)
    session = mgr.open("COM5")
    lines = [line async for line in mgr.stream(session.session_id)]
    assert any("Perdi a conexão" in line for line in lines)


# --- error translation on open ----------------------------------------------

def test_open_rejects_invalid_port_with_policy_error():
    mgr = SerialManager(serial_factory=FakeSerial, fake=False)
    with pytest.raises(PolicyError):
        mgr.open("/dev/ttyUSB0")


def test_open_rejects_unsupported_baud_with_policy_error():
    mgr = SerialManager(serial_factory=FakeSerial, fake=False)
    with pytest.raises(PolicyError, match="Baud rate"):
        mgr.open("COM5", 12345)


def test_open_translates_busy_error():
    def boom(**kwargs):
        raise Exception("Access is denied.")

    mgr = SerialManager(serial_factory=boom, fake=False)
    with pytest.raises(SerialError) as exc:
        mgr.open("COM5")
    assert "ocupada" in str(exc.value)


def test_open_translates_port_not_found_error():
    def boom(**kwargs):
        raise Exception("could not open port: no such file")

    mgr = SerialManager(serial_factory=boom, fake=False)
    with pytest.raises(SerialError) as exc:
        mgr.open("COM5")
    assert "Não achei a porta" in str(exc.value)


# --- fake mode stream is clearly labeled ------------------------------------

@pytest.mark.asyncio
async def test_fake_stream_is_labeled_simulation():
    mgr = SerialManager(fake=True)
    session = mgr.open("COM5", 115200)
    assert session.fake is True
    agen = mgr.stream(session.session_id)
    first = await agen.__anext__()
    assert "SIMULAÇÃO" in first
    await agen.aclose()
