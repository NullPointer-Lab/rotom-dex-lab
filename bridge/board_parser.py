from __future__ import annotations

import json
from typing import Any


def simplify_board_list(stdout: str) -> list[dict[str, Any]]:
    """Return child-friendly board choices from arduino-cli board list JSON/text.

    Arduino CLI output changed shape across versions, so this parser accepts the
    common JSON shapes and has a conservative text fallback.
    """
    text = stdout.strip()
    if not text:
        return []

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return _parse_text_board_list(text)

    rows = data if isinstance(data, list) else data.get("boards", []) if isinstance(data, dict) else []
    devices: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        port = _first_string(row, "address", "port", "port_address")
        if not port and isinstance(row.get("port"), dict):
            port = _first_string(row["port"], "address", "label")
        if not port:
            continue

        board_name = _board_name(row)
        devices.append(
            {
                "port": str(port).upper() if str(port).lower().startswith("com") else str(port),
                "name": board_name or "Placa Arduino/ESP32",
                "label": f"{board_name or 'Placa Arduino/ESP32'} em {port}",
                "isKnown": bool(board_name),
            }
        )
    return devices


def _first_string(obj: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = obj.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _board_name(row: dict[str, Any]) -> str | None:
    for key in ("name", "board_name"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    for key in ("matching_boards", "boards"):
        boards = row.get(key)
        if isinstance(boards, list) and boards:
            first = boards[0]
            if isinstance(first, dict):
                name = _first_string(first, "name", "label", "fqbn")
                if name:
                    return name
    return None


def _parse_text_board_list(text: str) -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.lower().startswith("port "):
            continue
        parts = line.split()
        port = next((part for part in parts if part.upper().startswith("COM")), None)
        if not port:
            continue
        name = " ".join(part for part in parts[1:] if not part.startswith("serial")) or "Placa Arduino/ESP32"
        devices.append(
            {
                "port": port.upper(),
                "name": name,
                "label": f"{name} em {port.upper()}",
                "isKnown": name != "Placa Arduino/ESP32",
            }
        )
    return devices
