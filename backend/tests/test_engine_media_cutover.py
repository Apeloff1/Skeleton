from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from core import expressive_tts
from routes import image_generation


ROOT = Path(__file__).resolve().parents[1]


class _FakeMediaClient:
    def __init__(self) -> None:
        self.generated = []
        self.variations = []
        self.edits = []
        self.speech = []

    async def generate_image(self, **kwargs):
        self.generated.append(kwargs)
        return {
            "provider": "openai",
            "model": "gpt-image-1",
            "images": [{"data": "aGVsbG8=", "format": "base64_png"}],
            "governance_decision_id": "gov-image",
            "admission_decision_id": "adm-image",
        }

    async def create_image_variation(self, image, **kwargs):
        self.variations.append((image, kwargs))
        return {
            "provider": "openai",
            "model": "image-variation",
            "images": [{"data": "aGVsbG8=", "format": "base64_png"}],
            "governance_decision_id": "gov-var",
            "admission_decision_id": "adm-var",
        }

    async def edit_image(self, image, **kwargs):
        self.edits.append((image, kwargs))
        return {
            "provider": "openai",
            "model": "image-edit",
            "images": [{"data": "aGVsbG8=", "format": "base64_png"}],
            "governance_decision_id": "gov-edit",
            "admission_decision_id": "adm-edit",
        }

    async def synthesize_speech(self, **kwargs):
        self.speech.append(kwargs)
        return {
            "provider": "openai",
            "model": "tts-1-hd",
            "response_format": "mp3",
            "audio": b"audio-bytes",
        }


@pytest.mark.asyncio
async def test_image_generation_delegates_to_engine(monkeypatch) -> None:
    fake = _FakeMediaClient()
    monkeypatch.setattr(
        image_generation.EngineClient,
        "from_env",
        classmethod(lambda cls, **kwargs: fake),
    )

    result = await image_generation.generate_with_openai(
        "draw a robot",
        "1024x1024",
        "standard",
        1,
    )

    assert result["status"] == "success"
    assert result["images"][0]["data"] == "aGVsbG8="
    assert fake.generated[0]["actor_id"] == "image-generation"
    assert fake.generated[0]["tenant_id"] == "default"
    assert fake.generated[0]["prompt"] == "draw a robot"


@pytest.mark.asyncio
async def test_image_variation_and_edit_delegate_to_engine(monkeypatch) -> None:
    fake = _FakeMediaClient()
    monkeypatch.setattr(
        image_generation.EngineClient,
        "from_env",
        classmethod(lambda cls, **kwargs: fake),
    )

    variation = await image_generation.create_variation(
        image_generation.ImageVariationRequest(
            image_base64="aGVsbG8=",
            provider="openai",
            count=1,
        )
    )
    assert variation["status"] == "success"
    assert fake.variations[0][0] == b"hello"

    edit = await image_generation.edit_image(
        image_generation.ImageEditRequest(
            image_base64="aGVsbG8=",
            mask_base64="bWFzaw==",
            prompt="make it blue",
            provider="openai",
        )
    )
    assert edit["status"] == "success"
    assert fake.edits[0][0] == b"hello"
    assert fake.edits[0][1]["mask"] == b"mask"


@pytest.mark.asyncio
async def test_expressive_tts_delegates_to_engine(monkeypatch) -> None:
    fake = _FakeMediaClient()
    monkeypatch.setattr(
        expressive_tts.EngineClient,
        "from_env",
        classmethod(lambda cls, **kwargs: fake),
    )

    result = await expressive_tts.generate_expressive_tts(
        "Hello there",
        tone="warm",
        shape=False,
    )

    assert result["audio_base64"] == "YXVkaW8tYnl0ZXM="
    assert result["format"] == "mp3"
    assert fake.speech[0]["actor_id"] == "expressive-tts"
    assert fake.speech[0]["tenant_id"] == "default"
    assert fake.speech[0]["text"] == "Hello there"


@pytest.mark.parametrize(
    "relative",
    (
        "routes/image_generation.py",
        "core/expressive_tts.py",
    ),
)
def test_media_surface_has_no_local_provider_activation(relative: str) -> None:
    source = (ROOT / relative).read_text(encoding="utf-8")

    assert "ProviderRegistry.from_env(" not in source
    assert "from core.ai_provider import" not in source
    assert "EngineClient" in source
