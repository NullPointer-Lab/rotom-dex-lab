import httpx
import pytest

from bridge.hermes_client import ERROR_REPLY, OFFLINE_REPLY, HermesClient


@pytest.mark.asyncio
async def test_offline_when_unconfigured():
    client = HermesClient(url=None)
    reply = await client.send_message("quero compilar", {})
    assert reply.offline is True
    assert reply.reply == OFFLINE_REPLY
    assert any(a["type"] == "arduino.compile" for a in reply.suggested_actions)


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
    assert HermesClient().configured is False
    assert HermesClient(url="https://x.test").configured is True
