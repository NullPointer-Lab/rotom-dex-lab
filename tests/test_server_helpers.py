from bridge.server import _board_choice_message


def test_unknown_single_board_requires_choice_message():
    devices = [{"port": "COM9", "name": "Placa Arduino/ESP32", "label": "Placa Arduino/ESP32 em COM9", "isKnown": False}]
    result = type("Result", (), {"exit_code": 0})()
    assert "não tenho certeza" in _board_choice_message(devices, result)
