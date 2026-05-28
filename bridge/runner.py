from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass
from typing import Sequence


@dataclass
class CommandResult:
    args: list[str]
    exit_code: int
    stdout: str
    stderr: str


class CommandRunner:
    def __init__(self, executable: str = "arduino-cli", timeout_seconds: int = 120):
        self.executable = executable
        self.timeout_seconds = timeout_seconds

    def find_executable(self) -> str | None:
        return shutil.which(self.executable)

    async def run(self, args: Sequence[str], timeout_seconds: int | None = None) -> CommandResult:
        if not args:
            raise ValueError("args cannot be empty")
        executable = self.find_executable() or self.executable
        cmd = [executable, *args]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return CommandResult(cmd, 127, "", f"Executável não encontrado: {self.executable}")
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_seconds or self.timeout_seconds
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return CommandResult(cmd, 124, "", "Comando excedeu timeout e foi interrompido.")
        return CommandResult(
            cmd,
            proc.returncode or 0,
            stdout_b.decode(errors="replace"),
            stderr_b.decode(errors="replace"),
        )
