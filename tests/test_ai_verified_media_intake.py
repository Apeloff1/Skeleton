"""Never conflate measured media decoding with trusted instructions or promotion."""
from dataclasses import replace
import hashlib
import io
import wave

import pytest

from skeleton.ai.runtime.multimodal.contracts import Modality
from skeleton.ai.runtime.multimodal.media_validation import (
    MediaValidationError,
    MediaValidationLimits,
)
from skeleton.ai.runtime.multimodal.verified_intake import (
    VerifiedMediaIntakeReceipt,
    verify_media_intake,
)


def pcm() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\x00\x01" * 800)
    return buf.getvalue()


def test_decoded_audio_bound_to_canonical_untrusted_intake() -> None:
    payload = pcm()
    result = verify_media_intake(
        asset_id="owner:clip-one", modality=Modality.AUDIO,
        mime_type="audio/wav", payload=payload,
        metadata={"source_id": "lab-1", "sample_rate_hz": 44100},
    )
    assert result.source_digest == hashlib.sha256(payload).hexdigest()
    assert result.asset.content_digest == result.measured.source_digest
    assert result.asset.content_bytes == result.measured.source_bytes
    assert result.asset.sanitized_metadata["sample_rate_hz"] == 44100
    assert result.measured_metadata["sample_rate"] == 8000
    assert result.measured_metadata["duration_ms"] == 100.0
    assert result.measured.format == "PCM_WAVE"
    assert not result.instruction_trusted
    assert not result.training_authorized
    assert not result.promotion_authorized
    assert result == verify_media_intake(
        asset_id="owner:clip-one", modality=Modality.AUDIO,
        mime_type="audio/wav", payload=payload,
        metadata={"source_id": "lab-1", "sample_rate_hz": 44100},
    )


def test_digest_binds_asset_identity_and_real_bytes() -> None:
    payload = pcm()
    def build(name: str):
        return verify_media_intake(asset_id=name, modality=Modality.AUDIO,
                                   mime_type="audio/wav", payload=payload)
    a, b = build("one"), build("two")
    assert a.source_digest == b.source_digest
    assert a.evidence_digest != b.evidence_digest
    with pytest.raises(MediaValidationError, match="digest mismatch"):
        replace(a, evidence_digest=b.evidence_digest)
    with pytest.raises(MediaValidationError, match="does not match"):
        replace(a, source_digest="a" * 64)
    with pytest.raises(MediaValidationError, match="digest mismatch"):
        replace(a, asset=b.asset)


@pytest.mark.parametrize("mime", [
    "audio/mp3", "audio/flac", "audio/x-wav", "image/png",
])
def test_mime_aliases_and_spoofing_fail_closed(mime: str) -> None:
    with pytest.raises(ValueError):
        verify_media_intake(asset_id="one", modality=Modality.AUDIO,
                            mime_type=mime, payload=pcm())


def test_unsupported_modalities_never_masquerade_as_measured_media() -> None:
    for modality in (Modality.DOCUMENT, Modality.SPEECH, Modality.VIDEO):
        with pytest.raises(MediaValidationError, match="supports image"):
            verify_media_intake(asset_id="one", modality=modality,
                                mime_type="audio/wav", payload=pcm())
    with pytest.raises(MediaValidationError, match="supports image"):
        verify_media_intake(asset_id="one", modality="audio",
                            mime_type="audio/wav", payload=pcm())


def test_invalid_limits_and_payload_fail_before_receipt() -> None:
    with pytest.raises(MediaValidationError):
        verify_media_intake(
            asset_id="one", modality=Modality.AUDIO, mime_type="audio/wav",
            payload=pcm(), limits=MediaValidationLimits(max_decoded_bytes=16),
        )
    with pytest.raises(ValueError):
        verify_media_intake(
            asset_id="one", modality=Modality.AUDIO, mime_type="audio/wav",
            payload=b"not-a-wave",
        )
    with pytest.raises(MediaValidationError, match="typed media"):
        verify_media_intake(
            asset_id="one", modality=Modality.AUDIO, mime_type="audio/wav",
            payload=pcm(), limits={"max_audio_bytes": 5},
        )


def test_unsupported_active_mime_never_calls_decoder() -> None:
    with pytest.raises(MediaValidationError, match="MIME"):
        verify_media_intake(
            asset_id="one", modality=Modality.IMAGE,
            mime_type="image/svg+xml", payload=b"<svg></svg>",
        )
