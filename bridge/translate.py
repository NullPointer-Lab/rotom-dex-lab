from __future__ import annotations

from .runner import CommandResult

SUCCESS_MESSAGES = {
    "compile": "Boa! O código passou no teste e está prontinho. ✅",
    "upload": "Enviei o código para a placa! 🚀 Agora é só testar.",
    "version": "O Arduino CLI está funcionando aqui no laboratório. ✅",
    "board_list": "Procura de placa concluída.",
}

DEFAULT_SUCCESS = "Deu tudo certo! ✅"


def friendly_arduino_message(result: CommandResult, action: str = "comando") -> str:
    """Translate an arduino-cli CommandResult into a child-friendly PT-BR message.

    Raw stdout/stderr is never hidden by this function; the caller keeps it and
    shows it under "Detalhes para o papai". This only produces the friendly line.
    """
    if result.exit_code == 0:
        return SUCCESS_MESSAGES.get(action, DEFAULT_SUCCESS)

    combined = f"{result.stderr}\n{result.stdout}".lower()

    if result.exit_code == 127 or "executável não encontrado" in combined or (
        "arduino-cli" in combined and "not found" in combined
    ):
        return (
            "Não achei o programa Arduino CLI no computador. Peça ao papai para instalar "
            "o Arduino CLI e tentar de novo."
        )

    if result.exit_code == 124 or "timeout" in combined:
        return "O comando demorou demais e eu parei. Tente de novo daqui a pouco."

    if any(
        phrase in combined
        for phrase in ("platform not installed", "core not installed", "not installed", "please install")
    ):
        return (
            "Falta instalar o pacote da placa (ESP32). Peça ao papai para rodar a instalação "
            "do core esp32 no Arduino CLI."
        )

    if any(phrase in combined for phrase in ("invalid fqbn", "unknown fqbn", "no such file or directory: fqbn")):
        return "O modelo da placa (FQBN) não está certo. Confira a placa escolhida."

    if any(
        phrase in combined
        for phrase in ("access is denied", "permission denied", "resource busy", "port busy", "could not open port")
    ):
        return (
            "A porta da placa está ocupada ou bloqueada. Feche o Arduino IDE ou o monitor "
            "serial e tente de novo."
        )

    # Missing library/header in the sketch (e.g. Adafruit_GFX.h, TFT_RoboEyes.h).
    # This must come BEFORE the port check: a "No such file" from a #include is a
    # missing library, NOT a missing serial port — confusing the two made Rotom
    # wrongly say "não achei a porta" while the board was connected fine.
    if "no such file or directory" in combined and ("fatal error" in combined or ".h" in combined):
        return (
            "Falta uma biblioteca que o projeto usa. Veja nos detalhes para o papai qual arquivo "
            ".h não foi encontrado e instale essa biblioteca."
        )

    if any(
        phrase in combined
        for phrase in (
            "port not found",
            "no device found",
            "cannot find the port",
            "no such port",
            "cannot find the file specified",
            "can't open device",
            "porta inválida",
        )
    ):
        return "Não achei a porta da placa. Conecte o cabo USB e procure a placa de novo."

    if "error:" in combined or "compilation error" in combined or "exit status" in combined:
        return (
            "O código tem um errinho e não passou no teste. Veja os detalhes para o papai "
            "para descobrir a linha do problema."
        )

    return "Algo não deu certo. Veja os detalhes para o papai e tente de novo."


def core_installed(core_list_stdout: str, fqbn: str) -> bool:
    """Best-effort check that the package/core for an FQBN is installed.

    `fqbn` looks like `esp32:esp32:esp32`; the package id is `esp32:esp32`.
    Accepts both `arduino-cli core list` text and JSON output.
    """
    package = ":".join(fqbn.split(":")[:2])
    if not package:
        return False
    return package.lower() in (core_list_stdout or "").lower()
