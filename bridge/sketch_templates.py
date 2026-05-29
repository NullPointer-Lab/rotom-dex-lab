from __future__ import annotations

from pathlib import Path
from typing import Any
import os

from .config import ProjectConfig
from .policy import PolicyError, _is_windows_style

TEMPLATES: dict[str, dict[str, str]] = {
    "motor-test": {
        "title": "Teste seguro de motor",
        "filename": "motor_test.ino",
        "description": "Sketch simples para testar um motor com rodas suspensas.",
        "content": """// {project_name} — teste seguro de motor\n// Levante as rodas antes de enviar este código.\n\nconst int MOTOR_PIN = 5;\n\nvoid setup() {{\n  Serial.begin(115200);\n  pinMode(MOTOR_PIN, OUTPUT);\n  Serial.println(\"Rotom Dex: teste de motor pronto!\");\n}}\n\nvoid loop() {{\n  Serial.println(\"Motor ligado por 1 segundo\");\n  digitalWrite(MOTOR_PIN, HIGH);\n  delay(1000);\n  Serial.println(\"Motor desligado por 2 segundos\");\n  digitalWrite(MOTOR_PIN, LOW);\n  delay(2000);\n}}\n""",
    },
    "serial-hello": {
        "title": "Olá pela serial",
        "filename": "serial_hello.ino",
        "description": "Sketch mínimo para confirmar que o monitor serial está lendo a placa.",
        "content": """// {project_name} — olá pela serial\n\nvoid setup() {{\n  Serial.begin(115200);\n}}\n\nvoid loop() {{\n  Serial.println(\"Oi, eu sou a placa do Davi!\");\n  delay(1000);\n}}\n""",
    },
}


def template_catalog() -> list[dict[str, str]]:
    return [
        {"id": template_id, "title": item["title"], "description": item["description"], "filename": item["filename"]}
        for template_id, item in TEMPLATES.items()
    ]


def render_template(template_id: str, *, project_name: str) -> dict[str, str]:
    item = TEMPLATES.get(template_id)
    if item is None:
        raise KeyError(template_id)
    return {
        "id": template_id,
        "title": item["title"],
        "description": item["description"],
        "filename": item["filename"],
        "content": item["content"].format(project_name=project_name),
    }


def create_template_file(template_id: str, project: ProjectConfig, *, confirmed: bool = False) -> dict[str, Any]:
    if not confirmed:
        raise PolicyError("Confirme antes de criar um sketch novo.")
    if _is_windows_style(project.root) and os.name != "nt":
        raise PolicyError(
            "Criação de template em caminho Windows só funciona no Windows do Davi. "
            "Use o preview aqui ou rode pelo atalho no computador dele."
        )
    rendered = render_template(template_id, project_name=project.name)
    root = Path(project.root).expanduser().resolve()
    if not root.is_dir():
        raise PolicyError(f"Pasta do projeto não existe: {root}")
    target = (root / rendered["filename"]).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise PolicyError("Template precisa ficar dentro da pasta do projeto.") from exc
    if target.exists():
        raise PolicyError(f"O arquivo já existe: {target.name}. Renomeie ou apague antes de criar de novo.")
    target.write_text(rendered["content"], encoding="utf-8")
    return {"ok": True, "path": str(target), "message": f"Criei o sketch {target.name} com segurança.", **rendered}
