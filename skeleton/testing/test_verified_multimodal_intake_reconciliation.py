"""Regression guards for true decoder-backed verification and bounded source identity."""
from __future__ import annotations

import io
import wave

import pytest

from skeleton.ai.runtime.multimodal.intake import (
    Modality,
    MultimodalIntake,
    MultimodalSanitizationError,
    VerifiedMultimodalAsset,
    verify_verified_asset,
)


def _pcm_wave() -> bytes:
    stream = io.BytesIO()
    with wave.open(stream, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"\x00\x00" * 80)
    return stream.getvalue()


def test_verified_audio_is_decoder_bound_and_replayable() -> None:
    payload = _pcm_wave()
    intake = MultimodalIntake(max_assets=2)
    asset = intake.sanitize_verified(
        asset_id="original-clip",
        modality=Modality.AUDIO,
        mime_type="audio/wav",
        payload=payload,
    )
    assert isinstance(asset, VerifiedMultimodalAsset)
    assert asset.validation.decoded_digest
    assert asset.validation.source_bytes == len(payload)
    assert not asset.instruction_trusted
    assert intake.sanitize_verified(
        asset_id="original-clip",
        modality=Modality.AUDIO,
        mime_type="audio/wav",
        payload=payload,
    ) is asset
    intake.verify_verified_asset(asset, payload)
    verify_verified_asset(asset, payload)


def test_verification_rejects_changed_source() -> None:
    payload = _pcm_wave()
    intake = MultimodalIntake()
    asset = intake.sanitize_verified(
        asset_id="a",
        modality=Modality.AUDIO,
        mime_type="audio/wav",
        payload=payload,
    )
    altered = bytearray(payload)
    altered[-2] ^= 1
    with pytest.raises(MultimodalSanitizationError):
        intake.verify_verified_asset(asset, bytes(altered))


def test_capacity_and_identity_binding_fail_closed() -> None:
    payload = _pcm_wave()
    intake = MultimodalIntake(max_assets=1)
    intake.sanitize(asset_id="one", modality=Modality.AUDIO, mime_type="audio/wav", payload=payload)
    with pytest.raises(MultimodalSanitizationError):
        intake.sanitize(asset_id="two", modality=Modality.AUDIO, mime_type="audio/wav", payload=payload)
    with pytest.raises(MultimodalSanitizationError):
        intake.sanitize(asset_id="one", modality=Modality.AUDIO, mime_type="audio/wav", payload=payload + b"!")
    with pytest.raises(MultimodalSanitizationError):
        MultimodalIntake(max_payload_bytes=True)
    with pytest.raises(MultimodalSanitizationError):
        MultimodalIntake(max_assets=0)


def test_malformed_payload_is_never_issued_as_verified() -> None:
    intake = MultimodalIntake()
    with pytest.raises(MultimodalSanitizationError):
        intake.sanitize_verified(
            asset_id="malformed",
            modality=Modality.AUDIO,
            mime_type="audio/wav",
            payload=b"RIFFbadnotwave",
        )
