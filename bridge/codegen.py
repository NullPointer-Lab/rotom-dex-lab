"""Vibecoding helpers: apply agent-proposed edits and version them with git.

Davi (9) builds his ESP32 project by describing changes in plain words. The
Rotom Dex agent answers with edit blocks; this module applies them to the
sketch and records every change as a git "save" the child can restore.

Edit format (robust for large sketches — no full-file regeneration):

    ARQUIVO: ZappRobotFinal.ino
    <<<<<<< BUSCAR
    <exact existing lines>
    =======
    <replacement lines>
    >>>>>>> SUBSTITUIR

Multiple blocks are allowed. A block whose BUSCAR text is empty creates/over-
writes the file. A non-empty BUSCAR must match exactly once, or that block is
reported as failed and skipped (never a fuzzy apply).
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

NO_CHANGES = "SEM_MUDANCAS"

_BLOCK_RE = re.compile(
    r"ARQUIVO:\s*(?P<file>.+?)\r?\n"
    r"<<<<<<<[ \t]*BUSCAR\r?\n"
    r"(?P<search>.*?)"
    r"\r?\n?=======\r?\n"
    r"(?P<replace>.*?)"
    r"\r?\n?>>>>>>>[ \t]*SUBSTITUIR",
    re.DOTALL,
)


class CodegenError(ValueError):
    """Raised on unsafe paths or git problems worth surfacing."""


@dataclass
class EditResult:
    applied: list[str] = field(default_factory=list)   # human notes for applied blocks
    failed: list[str] = field(default_factory=list)    # human notes for blocks that didn't match
    changed_files: list[str] = field(default_factory=list)


def parse_edits(text: str) -> list[dict[str, str]]:
    """Extract BUSCAR/SUBSTITUIR blocks from agent output."""
    if not isinstance(text, str):
        return []
    edits: list[dict[str, str]] = []
    for m in _BLOCK_RE.finditer(text):
        edits.append(
            {
                "file": m.group("file").strip().strip("`").strip(),
                "search": m.group("search"),
                "replace": m.group("replace"),
            }
        )
    return edits


def _safe_target(root: Path, rel: str) -> Path:
    """Resolve rel within root, rejecting absolute paths and traversal."""
    rel = rel.replace("\\", "/").strip()
    candidate = (root / rel).resolve()
    root_resolved = root.resolve()
    if root_resolved != candidate and root_resolved not in candidate.parents:
        raise CodegenError(f"Arquivo fora do projeto: {rel}")
    return candidate


def apply_edits(root: str | Path, edits: list[dict[str, str]]) -> EditResult:
    """Apply edits to files under root. Pure filesystem; no git here."""
    root_path = Path(root)
    result = EditResult()
    changed: dict[Path, str] = {}
    for i, edit in enumerate(edits, 1):
        rel = edit.get("file") or ""
        if not rel:
            result.failed.append(f"Bloco {i}: sem nome de arquivo.")
            continue
        try:
            target = _safe_target(root_path, rel)
        except CodegenError as exc:
            result.failed.append(f"Bloco {i}: {exc}")
            continue
        search = edit.get("search", "")
        replace = edit.get("replace", "")
        # Work against the latest in-memory version if the same file was edited.
        if target in changed:
            content = changed[target]
        elif target.exists():
            content = target.read_text(encoding="utf-8", errors="replace")
        else:
            content = None

        if not search.strip():
            # Empty BUSCAR -> create/overwrite the file.
            changed[target] = replace
            result.applied.append(f"Bloco {i}: criou/substituiu {rel}.")
            continue
        if content is None:
            result.failed.append(f"Bloco {i}: arquivo {rel} não existe.")
            continue
        occurrences = content.count(search)
        if occurrences == 0:
            result.failed.append(f"Bloco {i}: não achei o trecho em {rel}.")
            continue
        if occurrences > 1:
            result.failed.append(f"Bloco {i}: trecho aparece {occurrences} vezes em {rel}; ambíguo.")
            continue
        changed[target] = content.replace(search, replace)
        result.applied.append(f"Bloco {i}: alterei {rel}.")

    for target, content in changed.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
        result.changed_files.append(str(target.relative_to(root_path.resolve()) if target.is_relative_to(root_path.resolve()) else target))
    return result


# --- git versioning ---------------------------------------------------------

_HASH_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")
_UNIT = "\x1f"


def _git(root: str | Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=check,
    )


def is_repo(root: str | Path) -> bool:
    try:
        out = _git(root, "rev-parse", "--is-inside-work-tree", check=False)
        return out.returncode == 0 and out.stdout.strip() == "true"
    except (OSError, FileNotFoundError):
        return False


def ensure_repo(root: str | Path) -> None:
    if not is_repo(root):
        _git(root, "init", "-q")


def commit_all(root: str | Path, message: str) -> str | None:
    """Stage everything and commit. Returns short hash, or None if nothing changed."""
    ensure_repo(root)
    _git(root, "add", "-A")
    status = _git(root, "status", "--porcelain")
    if not status.stdout.strip():
        return None
    _git(
        root,
        "-c", "user.name=Davi (Rotom Dex)",
        "-c", "user.email=davi@rotom.local",
        "commit", "-q", "-m", message,
    )
    return _git(root, "rev-parse", "--short", "HEAD").stdout.strip()


def discard_changes(root: str | Path) -> None:
    """Undo uncommitted edits: revert tracked changes and drop new untracked files.

    Used to roll back to the last good save when a vibecoded change fails to
    compile, so the child is never left with broken code.
    """
    if not is_repo(root):
        return
    _git(root, "checkout", "--", ".", check=False)
    _git(root, "clean", "-fdq", check=False)


def list_versions(root: str | Path, limit: int = 30) -> list[dict[str, Any]]:
    if not is_repo(root):
        return []
    fmt = _UNIT.join(["%h", "%H", "%s", "%cI"])
    out = _git(root, "log", f"--pretty=format:{fmt}", "-n", str(limit), check=False)
    if out.returncode != 0 or not out.stdout.strip():
        return []
    head = _git(root, "rev-parse", "HEAD", check=False).stdout.strip()
    versions: list[dict[str, Any]] = []
    for line in out.stdout.splitlines():
        parts = line.split(_UNIT)
        if len(parts) != 4:
            continue
        short, full, subject, when = parts
        versions.append(
            {"short": short, "hash": full, "message": subject, "when": when, "current": full == head}
        )
    return versions


def restore_version(root: str | Path, commit_hash: str, label: str | None = None) -> dict[str, Any]:
    """Non-destructively restore files from a past commit as a NEW save.

    History is never rewritten: we check the old content out into the working
    tree and commit it on top, so every save (including this restore) stays
    recoverable.
    """
    if not _HASH_RE.match(commit_hash or ""):
        raise CodegenError("Versão inválida.")
    if not is_repo(root):
        raise CodegenError("Este projeto ainda não tem saves.")
    verify = _git(root, "cat-file", "-t", commit_hash, check=False)
    if verify.returncode != 0 or verify.stdout.strip() != "commit":
        raise CodegenError("Esse save não existe.")
    subject = _git(root, "log", "-1", "--pretty=%s", commit_hash, check=False).stdout.strip()
    short = _git(root, "rev-parse", "--short", commit_hash, check=False).stdout.strip()
    _git(root, "checkout", commit_hash, "--", ".")
    message = label or f"Voltei para o save {short}: {subject}"
    new_hash = commit_all(root, message)
    return {"restoredFrom": short, "restoredSubject": subject, "newSave": new_hash}
