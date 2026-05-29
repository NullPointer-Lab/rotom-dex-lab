import pytest

from bridge.board_parser import simplify_board_list


def test_simplify_board_list_from_json_auto_select_shape():
    stdout = '[{"address":"COM5","matching_boards":[{"name":"ESP32 Dev Module","fqbn":"esp32:esp32:esp32"}]}]'
    devices = simplify_board_list(stdout)
    assert devices == [
        {
            "port": "COM5",
            "name": "ESP32 Dev Module",
            "label": "ESP32 Dev Module em COM5",
            "isKnown": True,
        }
    ]


def test_simplify_board_list_from_dict_shape_multiple_devices():
    stdout = '{"boards":[{"port":{"address":"COM3"},"name":"ESP32"},{"port":{"address":"COM7"},"name":"Arduino Uno"}]}'
    devices = simplify_board_list(stdout)
    assert [device["port"] for device in devices] == ["COM3", "COM7"]
    assert devices[1]["label"] == "Arduino Uno em COM7"


def test_simplify_board_list_ignores_empty_output():
    assert simplify_board_list("") == []


def test_simplify_board_list_text_fallback():
    stdout = "Port Protocol Type Board Name FQBN Core\nCOM5 serial Serial Port ESP32 Dev Module esp32:esp32:esp32 esp32"
    devices = simplify_board_list(stdout)
    assert devices[0]["port"] == "COM5"


def test_simplify_board_list_from_detected_ports_shape_prefers_usb_serial():
    stdout = """
    {
      "detected_ports": [
        {
          "port": {
            "address": "COM5",
            "label": "COM5",
            "protocol": "serial",
            "protocol_label": "Serial Port",
            "properties": {}
          }
        },
        {
          "port": {
            "address": "COM9",
            "label": "COM9",
            "protocol": "serial",
            "protocol_label": "Serial Port (USB)",
            "properties": {
              "pid": "0x7523",
              "serialNumber": "",
              "vid": "0x1A86"
            }
          }
        }
      ]
    }
    """
    devices = simplify_board_list(stdout)
    assert [device["port"] for device in devices] == ["COM9", "COM5"]
    assert devices[0] == {
        "port": "COM9",
        "name": "USB-Serial CH340/CH341 (provável ESP32/Arduino)",
        "label": "USB-Serial CH340/CH341 (provável ESP32/Arduino) em COM9",
        "isKnown": True,
    }
