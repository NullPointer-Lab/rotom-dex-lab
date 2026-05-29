from bridge.server import _board_choice_message, _selected_board_port


def test_unknown_single_board_requires_choice_message():
    devices = [{"port": "COM9", "name": "Placa Arduino/ESP32", "label": "Placa Arduino/ESP32 em COM9", "isKnown": False}]
    result = type("Result", (), {"exit_code": 0})()
    assert "não tenho certeza" in _board_choice_message(devices, result)


def test_selected_board_port_uses_single_known_device_among_unknown_ports():
    devices = [
        {"port": "COM9", "name": "USB-Serial CH340/CH341", "label": "USB-Serial CH340/CH341 em COM9", "isKnown": True},
        {"port": "COM5", "name": "Placa Arduino/ESP32", "label": "Placa Arduino/ESP32 em COM5", "isKnown": False},
    ]
    assert _selected_board_port(devices) == "COM9"


def test_multiple_devices_message_names_likely_port():
    devices = [
        {"port": "COM9", "name": "USB-Serial CH340/CH341", "label": "USB-Serial CH340/CH341 em COM9", "isKnown": True},
        {"port": "COM5", "name": "Placa Arduino/ESP32", "label": "Placa Arduino/ESP32 em COM5", "isKnown": False},
    ]
    result = type("Result", (), {"exit_code": 0})()
    assert "mais provável" in _board_choice_message(devices, result)
    assert "COM9" in _board_choice_message(devices, result)
