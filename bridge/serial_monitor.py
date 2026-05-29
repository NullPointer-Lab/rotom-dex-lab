from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable

try:
    import serial  # type: ignore
except Exception:  # pragma: no cover - pyserial may be absent in some dev contexts
    serial = None

from .policy import PolicyError, validate_port

ALLOWED_BAUD_RATES = {9600, 57600, 74880, 115200}


class SerialError(Exception):
    """Raised when a serial port cannot be opened or read.

    The message is always a child-friendly PT-BR string safe to show in the UI.
    """


@dataclass
class SerialSession:
    session_id: str
    port: str
    baud: int
    fake: bool = False
    serial: Any | None = None
    running: bool = False
    lines: list[str] = field(default_factory=list)


class SerialManager:
    def __init__(
        self,
        *,
        serial_factory: Callable[..., Any] | None = None,
        fake: bool | None = None,
    ):
        self.sessions: dict[str, SerialSession] = {}
        self._serial_factory = serial_factory
        if fake is None:
            fake = os.environ.get("ROTOM_DEX_FAKE_SERIAL") == "1"
        self.fake = fake

    def open(self, port: str, baud: int = 115200) -> SerialSession:
        safe_port = validate_port(port)
        if baud not in ALLOWED_BAUD_RATES:
            raise PolicyError("Baud rate não permitido. Use 9600, 57600, 74880 ou 115200.")
        session_id = f"serial-{safe_port}-{baud}"
        existing = self.sessions.get(session_id)
        if existing:
            self.close(session_id)
        if self.fake:
            session = SerialSession(
                session_id=session_id, port=safe_port, baud=baud, fake=True, running=True
            )
        else:
            connection = self._open_serial(safe_port, baud)
            session = SerialSession(
                session_id=session_id,
                port=safe_port,
                baud=baud,
                fake=False,
                serial=connection,
                running=True,
            )
        self.sessions[session_id] = session
        return session

    def _open_serial(self, port: str, baud: int) -> Any:
        factory = self._serial_factory
        if factory is None:
            if serial is None:
                raise SerialError(
                    "A biblioteca de serial (pyserial) não está instalada. Peça ajuda ao papai."
                )
            factory = serial.Serial
        try:
            return factory(port=port, baudrate=baud, timeout=1)
        except Exception as exc:  # noqa: BLE001 - convert any driver error to friendly text
            raise SerialError(self._friendly_open_error(port, exc)) from exc

    @staticmethod
    def _friendly_open_error(port: str, exc: Exception) -> str:
        text = str(exc).lower()
        if any(word in text for word in ("permission", "access is denied", "busy", "in use")):
            return (
                f"A porta {port} está ocupada. Feche o Arduino IDE ou outro monitor "
                "serial e tente de novo."
            )
        if any(
            word in text
            for word in ("could not open", "no such", "filenotfound", "cannot find", "not found")
        ):
            return f"Não achei a porta {port}. Conecte a placa no cabo USB e procure de novo."
        return f"Não consegui abrir a porta {port}. Peça ajuda ao papai para conferir o cabo."

    def close(self, session_id: str) -> bool:
        session = self.sessions.pop(session_id, None)
        if not session:
            return False
        session.running = False
        if session.serial is not None:
            try:
                session.serial.close()
            except Exception:  # pragma: no cover - closing should not raise to the user
                pass
        return True

    def close_port(self, port: str) -> bool:
        """Close any open session on ``port`` (so an upload can take the port)."""
        target = (port or "").upper().strip()
        ids = [sid for sid, sess in self.sessions.items() if (sess.port or "").upper() == target]
        closed = False
        for sid in ids:
            if self.close(sid):
                closed = True
        return closed

    def clear(self, session_id: str) -> bool:
        session = self.sessions.get(session_id)
        if not session:
            return False
        session.lines.clear()
        return True

    def write(self, session_id: str, text: str) -> str:
        session = self.sessions.get(session_id)
        if not session or not session.running:
            raise SerialError("Monitor serial não está aberto. Abra o monitor de novo.")
        clean = text.strip()
        if not clean:
            raise SerialError("Digite uma mensagem antes de enviar para a placa.")
        if len(clean) > 200:
            raise SerialError("Mensagem muito grande para enviar pela serial.")
        if session.fake:
            session.lines.append(f"[SIMULAÇÃO] Davi enviou: {clean}")
        else:
            if session.serial is None:
                raise SerialError("Monitor serial não está conectado à placa.")
            try:
                session.serial.write((clean + "\n").encode("utf-8"))
            except Exception as exc:  # noqa: BLE001
                raise SerialError(f"Não consegui enviar pela serial: {self._friendly_open_error(session.port, exc)}") from exc
        return f"Enviei para a placa: {clean}"

    async def stream(self, session_id: str) -> AsyncIterator[str]:
        session = self.sessions.get(session_id)
        if session is None:
            return
        if session.fake:
            async for line in self._fake_stream(session):
                yield line
            return
        async for line in self._real_stream(session):
            yield line

    async def _real_stream(self, session: SerialSession) -> AsyncIterator[str]:
        connection = session.serial
        while session.running and connection is not None:
            try:
                raw = await asyncio.to_thread(connection.readline)
            except Exception as exc:  # noqa: BLE001
                yield f"[Rotom Dex] Perdi a conexão com a placa: {self._friendly_open_error(session.port, exc)}"
                session.running = False
                break
            if raw:
                line = raw.decode(errors="replace").rstrip("\r\n")
                session.lines.append(line)
                yield line
            else:
                # readline hit its timeout with no data; yield briefly to the loop.
                await asyncio.sleep(0.05)

    async def _fake_stream(self, session: SerialSession) -> AsyncIterator[str]:
        """Simulated stream, only used when ROTOM_DEX_FAKE_SERIAL=1 (dev mode)."""
        counter = 0
        while session.running:
            counter += 1
            line = f"[SIMULAÇÃO {session.port} @ {session.baud}] dado de teste {counter}"
            session.lines.append(line)
            yield line
            await asyncio.sleep(1)
