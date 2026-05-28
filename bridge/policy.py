from __future__ import annotations

import re
from pathlib import Path, PureWindowsPath

from .config import ProjectConfig

PORT_RE = re.compile(r"^COM([1-9][0-9]{0,2})$", re.IGNORECASE)


class PolicyError(ValueError):
    """Raised when a requested action violates the bridge policy."""


def validate_port(port: str) -> str:
    normalized = port.upper().strip()
    match = PORT_RE.match(normalized)
    if not match:
        raise PolicyError("Porta inválida. Use formato COM1..COM256.")
    number = int(match.group(1))
    if number > 256:
        raise PolicyError("Porta COM acima do limite permitido.")
    return normalized


def validate_fqbn(project: ProjectConfig, fqbn: str | None) -> str:
    selected = fqbn or project.defaultFqbn
    if selected not in project.allowedFqbns:
        raise PolicyError(f"FQBN não permitido para este projeto: {selected}")
    return selected


def _is_windows_style(path: str) -> bool:
    return bool(re.match(r"^[A-Za-z]:[\\/]", path))


def resolve_sketch_path(project: ProjectConfig, sketch_path: str | None = None) -> str:
    """Resolve and validate sketch path within project root.

    Supports Windows-style paths while running tests on Linux by using PureWindowsPath
    for policy checks when the configured root looks like C:/...
    """
    root = project.root
    requested = sketch_path or project.sketch

    if ".." in Path(requested).parts or ".." in PureWindowsPath(requested).parts:
        raise PolicyError("Caminho de sketch não pode conter '..'.")

    if _is_windows_style(root):
        win_root = PureWindowsPath(root)
        candidate = PureWindowsPath(requested)
        if candidate.is_absolute():
            full = candidate
        else:
            full = win_root / candidate
        try:
            full.relative_to(win_root)
        except ValueError as exc:
            raise PolicyError("Sketch precisa ficar dentro da pasta do projeto.") from exc
        return str(full)

    root_path = Path(root).expanduser().resolve()
    candidate_path = Path(requested).expanduser()
    full_path = candidate_path.resolve() if candidate_path.is_absolute() else (root_path / candidate_path).resolve()
    try:
        full_path.relative_to(root_path)
    except ValueError as exc:
        raise PolicyError("Sketch precisa ficar dentro da pasta do projeto.") from exc
    return str(full_path)
