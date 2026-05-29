import base64

import httpx
import pytest

from bridge.hermes_client import ERROR_REPLY
from bridge.vision import (
    ImageError,
    VisionClient,
    parse_image_data_url,
)

# 1x1 transparent PNG.
PNG_1PX = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)
PNG_DATA_URL = f"data:image/png;base64,{PNG_1PX}"

PROHIBITED_LOCAL_REPLY_TERMS = ("modo local", "não converso", "ia completa")


def assert_natural_reply(reply: str):
    lowered = reply.lower()
    for term in PROHIBITED_LOCAL_REPLY_TERMS:
        assert term not in lowered


# --- image validation -------------------------------------------------------

def test_parse_accepts_valid_png():
    mime, raw = parse_image_data_url(PNG_DATA_URL)
    assert mime == "image/png"
    assert raw == base64.b64decode(PNG_1PX)


def test_parse_rejects_non_data_url():
    with pytest.raises(ImageError):
        parse_image_data_url("https://example.com/cat.png")


def test_parse_rejects_non_image_mime():
    with pytest.raises(ImageError):
        parse_image_data_url("data:application/pdf;base64,aGVsbG8=")


def test_parse_rejects_missing_base64():
    with pytest.raises(ImageError):
        parse_image_data_url("data:image/png,notbase64")


def test_parse_rejects_oversized(monkeypatch):
    monkeypatch.setattr("bridge.vision.MAX_IMAGE_BYTES", 8)
    big = base64.b64encode(b"123456789").decode()  # 9 bytes > 8
    with pytest.raises(ImageError):
        parse_image_data_url(f"data:image/png;base64,{big}")


# --- offline (no provider configured) ---------------------------------------

@pytest.mark.asyncio
async def test_offline_with_image_is_honest_and_friendly():
    client = VisionClient(url=None)
    reply = await client.describe("o que é isso?", PNG_DATA_URL, {})
    assert reply.offline is True
    assert "imagem" in reply.reply.lower()
    assert_natural_reply(reply.reply)


@pytest.mark.asyncio
async def test_offline_text_only_uses_local_reply():
    client = VisionClient(url=None)
    reply = await client.describe("quero testar meu código", None, {})
    assert reply.offline is True
    assert "Testar código" in reply.reply
    assert any(a["type"] == "arduino.compile" for a in reply.suggested_actions)


# --- configured (mocked OpenAI-compatible backend) --------------------------

@pytest.mark.asyncio
async def test_configured_parses_reply_and_drops_invalid_actions():
    def handler(request):
        body = request.read().decode()
        assert "image_url" in body  # the image part was forwarded
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "Rotom! Vejo um LED no pino 2.\n"
                            "ACTIONS: arduino.compile, shell.exec, banana"
                        }
                    }
                ]
            },
        )

    client = VisionClient(
        url="https://vision.test/v1/chat/completions",
        token="abc",
        transport=httpx.MockTransport(handler),
    )
    reply = await client.describe("o que é isso?", PNG_DATA_URL, {})
    assert reply.offline is False
    assert "LED no pino 2" in reply.reply
    assert "ACTIONS:" not in reply.reply  # control line stripped
    # Only the known action survives; shell.exec and banana are dropped.
    assert [a["type"] for a in reply.suggested_actions] == ["arduino.compile"]


@pytest.mark.asyncio
async def test_configured_backend_error_falls_back_offline():
    def handler(request):
        return httpx.Response(500, json={"error": "boom"})

    client = VisionClient(
        url="https://vision.test/v1/chat/completions",
        transport=httpx.MockTransport(handler),
    )
    reply = await client.describe("oi", PNG_DATA_URL, {})
    assert reply.offline is True
    assert reply.reply == ERROR_REPLY


def test_configured_property(monkeypatch):
    monkeypatch.delenv("ROTOM_DEX_VISION_URL", raising=False)
    assert VisionClient().configured is False
    assert VisionClient(url="https://x.test").configured is True
