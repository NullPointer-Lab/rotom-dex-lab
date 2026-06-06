import asyncio

import httpx
import pytest

from bridge.hermes_client import ERROR_REPLY, LOCAL_CLI_ERROR_REPLY, OFFLINE_REPLY, HermesClient, local_reply_for

PROHIBITED_LOCAL_REPLY_TERMS = ("modo local", "não converso", "ia completa")


def assert_natural_local_reply(reply: str):
    lowered = reply.lower()
    for term in PROHIBITED_LOCAL_REPLY_TERMS:
        assert term not in lowered


@pytest.mark.asyncio
async def test_offline_when_unconfigured():
    client = HermesClient(url=None)
    reply = await client.send_message("quero compilar", {})
    assert reply.offline is True
    assert "Testar código" in reply.reply
    assert any(a["type"] == "arduino.compile" for a in reply.suggested_actions)


@pytest.mark.asyncio
async def test_offline_greeting_is_friendly_and_not_generic():
    client = HermesClient(url=None)
    reply = await client.send_message("Oi", {})
    assert reply.offline is True
    assert reply.reply.startswith("Oi, Davi!")
    assert reply.reply != OFFLINE_REPLY
    assert_natural_local_reply(reply.reply)
    assert "Começar" in reply.reply
    assert any(a["type"] == "arduino.board_list" for a in reply.suggested_actions)


def test_local_reply_for_known_intents():
    replies = [
        local_reply_for("status do papai"),
        local_reply_for("quero exemplo de motor"),
        local_reply_for("Rotom, procura minha placa"),
        local_reply_for("Rotom, testa meu projeto"),
        local_reply_for("abre o monitor serial"),
    ]
    assert "diagnóstico do papai" in replies[0].lower()
    assert "templates seguros" in replies[1]
    assert "procurar" in replies[2].lower()
    assert "testar" in replies[3].lower()
    assert "serial" in replies[4].lower()
    for reply in replies:
        assert_natural_local_reply(reply)
    assert_natural_local_reply(OFFLINE_REPLY)
    assert local_reply_for("missão aleatória") == OFFLINE_REPLY


@pytest.mark.asyncio
async def test_configured_success_uses_backend_reply():
    def handler(request):
        assert request.headers["authorization"] == "Bearer abc"
        return httpx.Response(
            200,
            json={
                "reply": "Vamos testar seu código!",
                "suggestedActions": [
                    {"type": "arduino.compile"},
                    {"type": "shell.exec"},  # must be dropped
                ],
            },
        )

    client = HermesClient(url="https://hermes.test/chat", token="abc", transport=httpx.MockTransport(handler))
    reply = await client.send_message("testa", {"project": {"id": "davibot"}})
    assert reply.offline is False
    assert reply.reply == "Vamos testar seu código!"
    assert [a["type"] for a in reply.suggested_actions] == ["arduino.compile"]


@pytest.mark.asyncio
async def test_backend_error_falls_back_offline():
    def handler(request):
        return httpx.Response(500, json={"error": "boom"})

    client = HermesClient(url="https://hermes.test/chat", transport=httpx.MockTransport(handler))
    reply = await client.send_message("oi", {})
    assert reply.offline is True
    assert reply.reply == ERROR_REPLY


@pytest.mark.asyncio
async def test_backend_timeout_falls_back_offline():
    def handler(request):
        raise httpx.ConnectTimeout("slow", request=request)

    client = HermesClient(url="https://hermes.test/chat", transport=httpx.MockTransport(handler))
    reply = await client.send_message("oi", {})
    assert reply.offline is True
    assert reply.reply == ERROR_REPLY


def test_configured_property(monkeypatch):
    monkeypatch.delenv("ROTOM_DEX_HERMES_URL", raising=False)
    monkeypatch.delenv("ROTOM_DEX_HERMES_LOCAL_CLI", raising=False)
    assert HermesClient().configured is False
    assert HermesClient(url="https://x.test").configured is True
    assert HermesClient(local_cli=True).configured is True


@pytest.mark.asyncio
async def test_local_cli_success_parses_reply_and_allowed_actions(monkeypatch):
    created = {}

    class FakeProcess:
        returncode = 0

        async def communicate(self):
            return (
                b"session_id: abc\nOi, Davi! Rotom online.\nACTIONS: arduino.compile, shell.exec\n",
                b"",
            )

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        created["cmd"] = cmd
        created["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    client = HermesClient(local_cli=True, hermes_bin="rotom", timeout_seconds=3)

    reply = await client.send_message("oi", {"history": []})

    assert reply.offline is False
    assert reply.reply == "Oi, Davi! Rotom online."
    assert [action["type"] for action in reply.suggested_actions] == ["arduino.compile"]
    assert created["cmd"][:3] == ("rotom", "chat", "-q")
    assert "--toolsets" in created["cmd"]
    assert "safe" in created["cmd"]


@pytest.mark.asyncio
async def test_local_cli_failure_is_honest_offline(monkeypatch):
    class FakeProcess:
        returncode = 2

        async def communicate(self):
            return (b"", b"boom")

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    client = HermesClient(local_cli=True, hermes_bin="rotom", timeout_seconds=3)

    reply = await client.send_message("oi", {})

    assert reply.offline is True
    assert reply.reply == LOCAL_CLI_ERROR_REPLY
