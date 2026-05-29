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

    rows = _json_rows(data)
    devices: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_port_info = row.get("port")
        port_info: dict[str, Any] = raw_port_info if isinstance(raw_port_info, dict) else {}
        port = _first_string(row, "address", "port", "port_address")
        if not port:
            port = _first_string(port_info, "address", "label")
        if not port:
            continue

        board_name = _board_name(row) or _known_usb_serial_name(port_info)
        normalized_port = str(port).upper() if str(port).lower().startswith("com") else str(port)
        reason = _device_reason(row, port_info, bool(board_name))
        confidence = "provavel" if board_name else "generica"
        devices.append(
            {
                "port": normalized_port,
                "name": board_name or "Porta serial genérica",
                "label": f"{board_name or 'Porta serial genérica'} em {normalized_port}",
                "isKnown": bool(board_name),
                "confidence": confidence,
                "reason": reason,
            }
        )
    return sorted(devices, key=lambda device: (not device.get("isKnown"), device["port"]))


def _json_rows(data: Any) -> list[Any]:
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in ("boards", "detected_ports"):
        rows = data.get(key)
        if isinstance(rows, list):
            return rows
    return []


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


def _known_usb_serial_name(port_info: dict[str, Any]) -> str | None:
    properties = port_info.get("properties") if isinstance(port_info.get("properties"), dict) else {}
    vid = str(properties.get("vid", "")).lower()
    pid = str(properties.get("pid", "")).lower()
    if (vid, pid) == ("0x1a86", "0x7523"):
        return "USB-Serial CH340/CH341 (provável ESP32/Arduino)"
    return None


def _format_hex_id(value: Any) -> str:
    text = str(value).strip()
    if not text:
        return ""
    if text.lower().startswith("0x"):
        return "0x" + text[2:].upper()
    return text.upper()


def _device_reason(row: dict[str, Any], port_info: dict[str, Any], is_known: bool) -> str:
    raw_properties = port_info.get("properties")
    properties: dict[str, Any] = raw_properties if isinstance(raw_properties, dict) else {}
    vid = _format_hex_id(properties.get("vid", ""))
    pid = _format_hex_id(properties.get("pid", ""))
    protocol = _first_string(port_info, "protocol_label", "protocol") or _first_string(row, "protocol_label", "protocol")
    parts: list[str] = []
    if protocol:
        parts.append(protocol)
    if vid or pid:
        parts.append(f"VID {vid or '?'} / PID {pid or '?'}")
    if is_known:
        parts.append("parece ser a placa do projeto")
    else:
        parts.append("porta serial encontrada; confirme antes de enviar")
    return " — ".join(parts)


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
                "confidence": "provavel" if name != "Placa Arduino/ESP32" else "generica",
                "reason": "Saída de texto do Arduino CLI; confirme antes de enviar",
            }
        )
    return devices
