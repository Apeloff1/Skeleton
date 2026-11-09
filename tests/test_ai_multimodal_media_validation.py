"""Verify bounded standard-library PCM validation without media execution."""
from __future__ import annotations

import hashlib
import io
import wave

import pytest

from skeleton.ai.runtime.multimodal.media_validation import (
    MediaValidationError,
    MediaValidationLimits,
    validate_media,
)


def _wave_bytes(*, channels: int = 1, rate: int = 8000, frames: int = 160) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setnchannels(channels)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(b"\x00\x01" * channels * frames)
    return output.getvalue()


def test_verified_pcm_receipt_reports_only_measured_properties() -> None:
    payload = _wave_bytes(channels=2, frames=800)
    receipt = validate_media(payload, modality="audio", mime_type="audio/wav")
    assert receipt.source_digest == hashlib.sha256(payload).hexdigest()
    assert receipt.media_type == "audio/wav"
    assert receipt.format == "PCM_WAVE"
    assert receipt.decoder_ref == "python.wave:integer-PCM:v1"
    assert receipt.channels == 2
    assert receipt.sample_rate_hz == 8000
    assert receipt.sample_count == 800
    assert receipt.sample_width_bytes == 2
    assert receipt.duration_seconds == 0.1
    assert receipt.decoded_bytes == 3200
    assert receipt.measured_metadata["frame_count"] == 800
    assert receipt.as_dict()["schema_version"] == "skeleton.ai.multimodal_media_validation.v1"
    assert len(receipt.digest) == 64


@pytest.mark.parametrize("mime", ["audio/mp3", "image/png", "audio/flac"])
def test_wave_cannot_be_relabelled_as_another_media_format(mime: str) -> None:
    with pytest.raises(MediaValidationError):
        validate_media(_wave_bytes(), modality="audio", mime_type=mime)


def test_container_length_and_payload_integrity_fail_closed() -> None:
    payload = _wave_bytes()
    with pytest.raises(MediaValidationError):
        validate_media(payload[:-1], modality="audio", mime_type="audio/wav")
    with pytest.raises(MediaValidationError):
        validate_media(b"RIFX" + payload[4:], modality="audio", mime_type="audio/wav")
    with pytest.raises(MediaValidationError):
        validate_media(b"", modality="audio", mime_type="audio/wav")
    with pytest.raises(MediaValidationError):
        validate_media(bytearray(payload), modality="audio", mime_type="audio/wav")


def test_stricter_local_limits_reject_audio_without_readiness_claim() -> None:
    payload = _wave_bytes(frames=800)
    with pytest.raises(MediaValidationError):
        validate_media(
            payload, modality="audio", mime_type="audio/wav",
            limits=MediaValidationLimits(max_audio_seconds=1, max_decoded_bytes=100),
        )
    with pytest.raises(MediaValidationError):
        MediaValidationLimits(max_audio_channels=0)
    with pytest.raises(MediaValidationError):
        validate_media(payload, modality="video", mime_type="audio/wav")


def test_unsupported_image_format_is_rejected_before_pillow_decode() -> None:
    with pytest.raises(MediaValidationError):
        validate_media(b"GIF89a" + b"\x00" * 64,
                       modality="image", mime_type="image/gif")
