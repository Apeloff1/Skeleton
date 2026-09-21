from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from skeleton.vault.data_lifecycle import GovernedDataRecord
from skeleton.vault.governance_registry import GovernanceRegistry

from core.ai_provider import (
    OpenAIProviderAdapter,
    ProviderImageRequest,
    ProviderPolicyError,
    ProviderSpeechRequest,
)


ROOT = Path(__file__).resolve().parents[2]


class _FakeImages:
    def __init__(self) -> None:
        self.generate_kwargs = None
        self.variation_kwargs = None
        self.edit_kwargs = None

    async def generate(self, **kwargs):
        self.generate_kwargs = kwargs
        return SimpleNamespace(
            id="img_gen_1",
            data=[
                SimpleNamespace(
                    b64_json="aGVsbG8=",
                    revised_prompt="revised prompt",
                )
            ],
        )

    async def create_variation(self, **kwargs):
        self.variation_kwargs = kwargs
        return SimpleNamespace(
            id="img_var_1",
            data=[SimpleNamespace(b64_json="dmFyaWF0aW9u")],
        )

    async def edit(self, **kwargs):
        self.edit_kwargs = kwargs
        return SimpleNamespace(
            id="img_edit_1",
            data=[SimpleNamespace(b64_json="ZWRpdA==")],
        )


class _FakeSpeech:
    def __init__(self) -> None:
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            id="speech_1",
            content=b"fake-mp3",
        )


class _FakeAudio:
    def __init__(self, speech: _FakeSpeech) -> None:
        self.speech = speech


class _FakeClient:
    def __init__(self) -> None:
        self.images = _FakeImages()
        self.speech = _FakeSpeech()
        self.audio = _FakeAudio(self.speech)


@pytest.mark.asyncio
async def test_image_generation_uses_canonical_provider_runtime() -> None:
    client = _FakeClient()
    adapter = OpenAIProviderAdapter(
        api_key="test-key",
        model="text-model",
        client=client,
    )

    result = await adapter.generate_image(
        ProviderImageRequest(
            prompt="a test image",
            size="1024x1024",
            quality="standard",
            count=1,
            model="gpt-image-1",
            purpose="image-generation",
        )
    )

    assert result.provider == "openai"
    assert result.model == "gpt-image-1"
    assert result.request_id == "img_gen_1"
    assert result.images[0]["data"] == "aGVsbG8="
    assert result.images[0]["revised_prompt"] == "revised prompt"
    assert result.governance_decision_id
    assert result.admission_decision_id
    assert client.images.generate_kwargs == {
        "model": "gpt-image-1",
        "prompt": "a test image",
        "size": "1024x1024",
        "quality": "standard",
        "n": 1,
        "response_format": "b64_json",
    }


@pytest.mark.asyncio
async def test_image_variation_and_edit_remain_inside_provider_boundary() -> None:
    client = _FakeClient()
    adapter = OpenAIProviderAdapter(
        api_key="test-key",
        model="text-model",
        client=client,
    )

    variation = await adapter.create_image_variation(
        b"source-image",
        count=2,
        operation_id="variation-op",
    )
    edited = await adapter.edit_image(
        b"source-image",
        prompt="add a blue sky",
        mask=b"mask",
        operation_id="edit-op",
    )

    assert variation.provider == "openai"
    assert variation.request_id == "img_var_1"
    assert variation.images[0]["data"] == "dmFyaWF0aW9u"
    assert variation.governance_decision_id
    assert variation.admission_decision_id
    assert client.images.variation_kwargs["n"] == 2

    assert edited.provider == "openai"
    assert edited.request_id == "img_edit_1"
    assert edited.images[0]["data"] == "ZWRpdA=="
    assert edited.governance_decision_id
    assert edited.admission_decision_id
    assert client.images.edit_kwargs["prompt"] == "add a blue sky"
    assert "mask" in client.images.edit_kwargs


@pytest.mark.asyncio
async def test_speech_synthesis_uses_canonical_provider_runtime() -> None:
    client = _FakeClient()
    adapter = OpenAIProviderAdapter(
        api_key="test-key",
        model="text-model",
        client=client,
    )

    result = await adapter.synthesize_speech(
        ProviderSpeechRequest(
            text="Read this aloud.",
            voice="nova",
            speed=0.95,
            model="tts-1-hd",
            response_format="mp3",
            purpose="speech-synthesis",
        )
    )

    assert result.provider == "openai"
    assert result.model == "tts-1-hd"
    assert result.response_format == "mp3"
    assert result.audio == b"fake-mp3"
    assert result.request_id == "speech_1"
    assert result.governance_decision_id
    assert result.admission_decision_id
    assert client.speech.kwargs == {
        "model": "tts-1-hd",
        "voice": "nova",
        "input": "Read this aloud.",
        "speed": 0.95,
        "response_format": "mp3",
    }


@pytest.mark.parametrize(
    "relative",
    [
        "backend/routes/image_generation.py",
        "backend/routes/ai_reader.py",
        "backend/routes/ai_pipeline.py",
        "backend/core/expressive_tts.py",
        "backend/routes/ai_debugger.py",
        "backend/routes/ai_toolkit_enhanced.py",
    ],
)
def test_application_surfaces_do_not_own_provider_credentials_or_sdks(relative: str) -> None:
    source = (ROOT / relative).read_text(encoding="utf-8")
    forbidden = (
        "EMERGENT_LLM_KEY",
        "OPENAI_API_KEY",
        "from openai import",
        "import openai",
        "from emergentintegrations.llm.openai import",
    )
    hits = [token for token in forbidden if token in source]
    assert hits == [], f"{relative} bypasses canonical provider runtime: {hits}"


def _media_governance_context(
    *,
    record_id: str,
    purpose: str,
    data_class: str = "restricted",
):
    registry = GovernanceRegistry()
    registry.register(
        GovernedDataRecord(
            record_id=record_id,
            tenant_id="tenant-media",
            owner_plane="artifact-files",
            source_ref=f"artifact:{record_id}",
            data_class=data_class,
            purposes=(purpose,),
            deletion_targets=("artifact",),
            created_at=1.0,
        )
    )
    return registry.context_for(
        (record_id,),
        tenant_id="tenant-media",
        purpose=purpose,
    )


@pytest.mark.asyncio
async def test_image_generation_honors_registry_classification_before_io() -> None:
    client = _FakeClient()
    adapter = OpenAIProviderAdapter(
        api_key="test-key",
        model="text-model",
        client=client,
    )
    context = _media_governance_context(
        record_id="restricted-image",
        purpose="image-generation",
    )

    with pytest.raises(ProviderPolicyError, match="governance policy"):
        await adapter.generate_image(
            ProviderImageRequest(
                prompt="do not transmit",
                data_class="public",
                purpose="image-generation",
                governance_context=context,
            )
        )

    assert client.images.generate_kwargs is None


@pytest.mark.asyncio
async def test_speech_honors_registry_classification_before_io() -> None:
    client = _FakeClient()
    adapter = OpenAIProviderAdapter(
        api_key="test-key",
        model="text-model",
        client=client,
    )
    context = _media_governance_context(
        record_id="restricted-speech",
        purpose="speech-synthesis",
    )

    with pytest.raises(ProviderPolicyError, match="governance policy"):
        await adapter.synthesize_speech(
            ProviderSpeechRequest(
                text="do not transmit",
                data_class="public",
                purpose="speech-synthesis",
                governance_context=context,
            )
        )

    assert client.speech.kwargs is None
