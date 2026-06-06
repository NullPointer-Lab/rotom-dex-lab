#!/usr/bin/env python3
"""Gera firmware/ZappClockOnly/wifi_secrets.h a partir do .env.

Formato esperado no .env da raiz do projeto:

wifi=nome_da_rede
passwd=senha_da_rede

Este script nao imprime a senha. O header gerado esta no .gitignore.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
OUT_PATH = ROOT / "firmware" / "ZappClockOnly" / "wifi_secrets.h"


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        values[key] = value
    return values


def cpp_escape(value: str) -> str:
    return (
        value
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "")
    )


def main() -> int:
    if not ENV_PATH.exists():
        print(f"ERRO: .env nao encontrado em {ENV_PATH}")
        return 1

    values = parse_env(ENV_PATH)
    ssid = values.get("wifi", "")
    password = values.get("passwd", "")

    if not ssid or not password:
        found = ", ".join(sorted(values)) or "nenhuma"
        print(f"ERRO: .env precisa das chaves wifi e passwd. Chaves encontradas: {found}")
        return 1

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        "// Arquivo gerado automaticamente por scripts/generate_wifi_header.py\n"
        "// Nao editar manualmente. Nao enviar para git.\n"
        "#pragma once\n\n"
        f'const char* ZAPP_WIFI_SSID = "{cpp_escape(ssid)}";\n'
        f'const char* ZAPP_WIFI_PASSWORD = "{cpp_escape(password)}";\n',
        encoding="utf-8",
    )

    print(f"wifi_secrets.h gerado com SSID definido e senha protegida: {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
