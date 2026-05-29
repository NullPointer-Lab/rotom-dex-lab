from bridge.actions import local_actions_for, normalize_action, normalize_actions


def test_normalize_action_enforces_confirmation_from_table():
    # AI tries to disable the upload guard; server must override it.
    action = normalize_action({"type": "arduino.upload", "requiresConfirmation": False})
    assert action["requiresConfirmation"] is True
    assert action["type"] == "arduino.upload"
    assert action["params"] == {}


def test_normalize_action_uses_default_label_when_missing():
    action = normalize_action({"type": "arduino.compile"})
    assert action["label"] == "Testar o código agora"
    assert action["requiresConfirmation"] is False


def test_normalize_action_rejects_unknown_type():
    assert normalize_action({"type": "shell.exec", "params": {"cmd": "rm -rf"}}) is None
    assert normalize_action("not a dict") is None


def test_normalize_actions_drops_unknown_and_dedupes():
    raw = [
        {"type": "arduino.compile"},
        {"type": "evil.action"},
        {"type": "arduino.compile"},
        {"type": "arduino.upload"},
    ]
    result = normalize_actions(raw)
    assert [a["type"] for a in result] == ["arduino.compile", "arduino.upload"]


def test_local_actions_for_keywords():
    types = [a["type"] for a in local_actions_for("Rotom, quero enviar para a placa")]
    assert "arduino.upload" in types
    # always returns at least something usable
    assert local_actions_for("oi") != []
