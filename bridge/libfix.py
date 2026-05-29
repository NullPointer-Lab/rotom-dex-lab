"""Auto-heal missing Arduino libraries from compile errors.

When a sketch fails to compile with ``fatal error: Foo.h: No such file or
directory``, Rotom can usually fix it for Davi by finding the library that
provides that header in the Arduino catalog and installing it. This module has
the pure (testable) parts; the actual install/recompile loop lives in the server
(it needs the ArduinoService).
"""
from __future__ import annotations

import json
import re

_HEADER_RE = re.compile(r"fatal error:\s*([^\s:]+\.h)\b", re.IGNORECASE)

# Fast, reliable mapping for headers whose catalog entry doesn't advertise
# `provides_includes` in search results (so search alone wouldn't find them).
KNOWN_HEADERS: dict[str, str] = {
    "adafruit_gfx.h": "Adafruit GFX Library",
    "adafruit_st7735.h": "Adafruit ST7735 and ST7789 Library",
    "adafruit_st7789.h": "Adafruit ST7735 and ST7789 Library",
    "adafruit_ssd1306.h": "Adafruit SSD1306",
    "adafruit_neopixel.h": "Adafruit NeoPixel",
    "adafruit_sensor.h": "Adafruit Unified Sensor",
    "dht.h": "DHT sensor library",
    "fastled.h": "FastLED",
    "arduinojson.h": "ArduinoJson",
    "liquidcrystal_i2c.h": "LiquidCrystal I2C",
    "tft_roboeyes.h": "TFT_RoboEyes",
}


def missing_headers(text: str) -> list[str]:
    """Return the distinct missing header filenames from compile output."""
    out: list[str] = []
    lowered_seen: set[str] = set()
    for match in _HEADER_RE.finditer(text or ""):
        header = re.split(r"[\\/]", match.group(1))[-1]
        if header.lower() not in lowered_seen:
            lowered_seen.add(header.lower())
            out.append(header)
    return out


def known_library(header: str) -> str | None:
    return KNOWN_HEADERS.get(header.lower())


def _includes_of(lib: dict) -> list[str]:
    includes: list[str] = list(lib.get("provides_includes") or [])
    latest = lib.get("latest")
    if isinstance(latest, dict):
        includes += list(latest.get("provides_includes") or [])
    releases = lib.get("releases")
    if isinstance(releases, dict):
        for rel in releases.values():
            if isinstance(rel, dict):
                includes += list(rel.get("provides_includes") or [])
    return includes


def pick_library_from_search(search_stdout: str, header: str) -> str | None:
    """From ``arduino-cli lib search --format json`` output, return the library
    name that provides ``header`` (exact include match), or None."""
    try:
        data = json.loads(search_stdout)
    except (ValueError, TypeError):
        return None
    target = re.split(r"[\\/]", header)[-1].lower()
    for lib in data.get("libraries") or []:
        for inc in _includes_of(lib):
            if re.split(r"[\\/]", inc)[-1].lower() == target:
                return lib.get("name")
    return None
