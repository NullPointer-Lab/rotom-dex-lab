from __future__ import annotations

from .config import ProjectConfig
from .policy import resolve_sketch_path, validate_fqbn, validate_port
from .runner import CommandResult, CommandRunner


class ArduinoService:
    def __init__(self, runner: CommandRunner | None = None):
        self.runner = runner or CommandRunner()

    async def version(self) -> CommandResult:
        return await self.runner.run(["version"], timeout_seconds=20)

    async def board_list(self, json_format: bool = False) -> CommandResult:
        args = ["board", "list"]
        if json_format:
            args.extend(["--format", "json"])
        return await self.runner.run(args, timeout_seconds=30)

    async def core_list(self) -> CommandResult:
        return await self.runner.run(["core", "list"], timeout_seconds=30)

    async def compile(self, project: ProjectConfig, fqbn: str | None = None, sketch_path: str | None = None) -> CommandResult:
        safe_fqbn = validate_fqbn(project, fqbn)
        safe_sketch = resolve_sketch_path(project, sketch_path)
        return await self.runner.run(["compile", "--fqbn", safe_fqbn, safe_sketch], timeout_seconds=180)

    async def upload(
        self,
        project: ProjectConfig,
        port: str,
        confirmed: bool,
        fqbn: str | None = None,
        sketch_path: str | None = None,
    ) -> CommandResult:
        if not confirmed:
            return CommandResult([], 2, "", "Upload requer confirmação explícita.")
        safe_port = validate_port(port)
        safe_fqbn = validate_fqbn(project, fqbn)
        safe_sketch = resolve_sketch_path(project, sketch_path)
        return await self.runner.run(
            ["upload", "-p", safe_port, "--fqbn", safe_fqbn, safe_sketch],
            timeout_seconds=180,
        )
