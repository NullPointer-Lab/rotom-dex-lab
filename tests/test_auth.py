from bridge.auth import SessionAuth


def test_uses_provided_token():
    auth = SessionAuth(token="segredo")
    assert auth.token == "segredo"
    assert auth.check("segredo") is True
    assert auth.check("errado") is False
    assert auth.check(None) is False
    assert auth.check("") is False


def test_reads_token_from_env(monkeypatch):
    monkeypatch.setenv("ROTOM_DEX_SESSION_TOKEN", "do-env")
    auth = SessionAuth()
    assert auth.token == "do-env"


def test_generates_token_when_absent(monkeypatch):
    monkeypatch.delenv("ROTOM_DEX_SESSION_TOKEN", raising=False)
    auth = SessionAuth()
    assert auth.token
    assert len(auth.token) >= 16
