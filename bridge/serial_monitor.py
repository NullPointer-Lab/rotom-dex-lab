from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

try:
    import serial  # type: ignore
except Exception:  # pragma: no cover - pyserial may be absent in some dev contexts
    serial = None

from .policy import validate_port


@dataclass
class SerialSession:
    session_id: str
    port: str
    baud: int
    lines: list[str] = field(default_factory=list)
    running: bool = False


class SerialManager:
    def __init__(self):
        self.sessions: dict[str, SerialSession] = {}

    def open(self, port: str, baud: int = 115200) -> SerialSession:
        safe_port = validate_port(port)
        session_id = f"serial-{safe_port}-{baud}"
        session = SerialSession(session_id=session_id, port=safe_port, baud=baud, running=True)
        self.sessions[session_id] = session
        return session

    def close(self, session_id: str) -> bool:
        session = self.sessions.get(session_id)
        if not session:
            return False
        session.running = False
        return True

    async def fake_stream(self, session_id: str):
        """Development stream placeholder. Real Windows serial streaming comes next."""
        session = self.sessions[session_id]
        counter = 0
        while session.running:
            counter += 1
            line = f"[{session.port} @ {session.baud}] aguardando dados... {counter}"
            session.lines.append(line)
            yield line
            await asyncio.sleep(1)
