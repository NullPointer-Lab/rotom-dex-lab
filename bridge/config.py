from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ProjectConfig(BaseModel):
    id: str
    name: str
    root: str
    sketch: str
    allowedFqbns: list[str] = Field(default_factory=list)
    defaultFqbn: str
    defaultBaud: int = 115200


class AppConfig(BaseModel):
    defaultProjectId: str
    projects: list[ProjectConfig]

    def get_project(self, project_id: str | None = None) -> ProjectConfig:
        wanted = project_id or self.defaultProjectId
        for project in self.projects:
            if project.id == wanted:
                return project
        raise KeyError(f"Projeto não configurado: {wanted}")


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(path) if path else Path(__file__).resolve().parents[1] / "config" / "projects.json"
    data: dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8"))
    return AppConfig.model_validate(data)


def load_missions(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Load the mission/progress list. Returns [] if the file is missing/invalid."""
    config_path = Path(path) if path else Path(__file__).resolve().parents[1] / "config" / "missions.json"
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    missions = data.get("missions") if isinstance(data, dict) else None
    if not isinstance(missions, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for mission in missions:
        if not isinstance(mission, dict):
            continue
        title = mission.get("title")
        if not isinstance(title, str) or not title.strip():
            continue
        status = mission.get("status")
        if status not in ("done", "doing", "todo"):
            status = "todo"
        cleaned.append(
            {
                "id": str(mission.get("id") or title),
                "title": title.strip(),
                "status": status,
            }
        )
    return cleaned
