from __future__ import annotations

import base64

import httpx
import pytest

from core.engine_client import EngineClient, EngineClientConfig, EngineProtocolError


_SERVICE_TOKEN = "test-engine-media-client-" + ("x" * 40)


def _client(handler):
    return EngineClient(
        EngineClientConfig(
            base_url="http://skeleton:8001",
            service_token=_SERVICE_TOKEN,
            service_principal="backend-service",
            request_timeout_s=2,
            max_response_bytes=1024 * 1024,
            max_media_response_bytes=16 * 1024 * 1024,
        ),
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.asyncio
async def test_generate_image_uses_media_endpoint_and_validates_base64() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers["authorization"]
        seen["principal"] = request.headers["x-zaibatsu-attester"]
        seen["body"] = request.read().decode("utf-8")
        return httpx.Response(
            200,
            json={
                "provider": "openai",
                "model": "gpt-image-1",
                "images": [
                    {
                        "data": base64.b64encode(b"image-bytes").decode("ascii"),
                        "format": "base64_png",
                    }
                ],
            },
        )

    client = _client(handler)
    payload = await client.generate_image(
        actor_id="image-route",
        tenant_id="tenant-a",
        operation_id="img-op",
        prompt="draw a robot",
    )

    assert seen["path"] == "/api/v1/engine/media/images/generate"
    assert seen["auth"] == "Bearer " + _SERVICE_TOKEN
    assert seen["principal"] == "backend-service"
    assert payload["images"][0]["data"] == "aW1hZ2UtYnl0ZXM="


@pytest.mark.asyncio
async def test_generate_image_rejects_malformed_base64() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "provider": "openai",
                "model": "gpt-image-1",
                "images": [{"data": "not***base64"}],
            },
        )

    with pytest.raises(EngineProtocolError, match="invalid base64"):
        await _client(handler).generate_image(
            actor_id="image-route",
            tenant_id="tenant-a",
            operation_id="img-op",
            prompt="draw",
        )


@pytest.mark.asyncio
async def test_variation_and_edit_encode_binary_media() -> None:
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append((request.url.path, request.read().decode("utf-8")))
        return httpx.Response(
            200,
            json={
                "provider": "openai",
                "model": "image-op",
                "images": [{"data": "aGVsbG8="}],
            },
        )

    client = _client(handler)
    await client.create_image_variation(
        b"source-image",
        actor_id="image-route",
        tenant_id="tenant-a",
        operation_id="var-op",
    )
    await client.edit_image(
        b"source-image",
        prompt="edit",
        actor_id="image-route",
        tenant_id="tenant-a",
        operation_id="edit-op",
        mask=b"mask",
    )

    assert bodies[0][0] == "/api/v1/engine/media/images/variation"
    assert base64.b64encode(b"source-image").decode("ascii") in bodies[0][1]
    assert bodies[1][0] == "/api/v1/engine/media/images/edit"
    assert base64.b64encode(b"mask").decode("ascii") in bodies[1][1]


@pytest.mark.asyncio
async def test_variation_and_edit_reject_malformed_image_payloads() -> None:
    def bad(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "provider": "openai",
                "model": "image-op",
                "images": [{"data": "not***base64"}],
            },
        )

    client = _client(bad)
    with pytest.raises(EngineProtocolError, match="invalid base64"):
        await client.create_image_variation(
            b"source-image",
            actor_id="image-route",
            tenant_id="tenant-a",
            operation_id="var-op",
        )
    with pytest.raises(EngineProtocolError, match="invalid base64"):
        await client.edit_image(
            b"source-image",
            prompt="edit",
            actor_id="image-route",
            tenant_id="tenant-a",
            operation_id="edit-op",
        )


@pytest.mark.asyncio
async def test_speech_decodes_audio_and_rejects_bad_payload() -> None:
    def good(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "provider": "openai",
                "model": "tts-1-hd",
                "response_format": "mp3",
                "audio_base64": base64.b64encode(b"audio").decode("ascii"),
            },
        )

    payload = await _client(good).synthesize_speech(
        actor_id="tts",
        tenant_id="tenant-a",
        operation_id="speech-op",
        text="hello",
    )
    assert payload["audio"] == b"audio"

    def bad(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "provider": "openai",
                "model": "tts-1-hd",
                "response_format": "mp3",
                "audio_base64": "not***base64",
            },
        )

    with pytest.raises(EngineProtocolError, match="invalid base64"):
        await _client(bad).synthesize_speech(
            actor_id="tts",
            tenant_id="tenant-a",
            operation_id="speech-op",
            text="hello",
        )
