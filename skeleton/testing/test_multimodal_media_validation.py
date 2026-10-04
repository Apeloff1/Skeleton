from __future__ import annotations

import builtins
import hashlib
import io
import random
import struct
import wave
import zlib
from dataclasses import replace

import pytest
from PIL import Image, ImageFile

from skeleton.ai.runtime.multimodal.intake import (
    Modality,
    MultimodalIntake,
    MultimodalSanitizationError,
    VerifiedMultimodalAsset,
    verify_verified_asset,
)
from skeleton.ai.runtime.multimodal.media_validation import (
    MediaValidationError,
    MediaValidationLimits,
    validate_media,
)


def _image(format="PNG", size=(3, 2), mode="RGB"):
    output = io.BytesIO()
    with Image.new(mode, size, 1) as image:
        image.save(output, format=format)
    return output.getvalue()


def _audio(*, channels=1, rate=8000, width=2, frames=800):
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(width)
        writer.setframerate(rate)
        writer.writeframes(b"\x01" * frames * channels * width)
    return output.getvalue()


def _chunk(kind, data):
    return (
        struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def _png(*, width=1, height=1, decoded=b"\0\xff\0\0", tail=b"", prefix=()):
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + b"".join(prefix)
        + _chunk(b"IDAT", zlib.compress(decoded))
        + _chunk(b"IEND", b"")
        + tail
    )


def _admit(payload, *, modality=Modality.IMAGE, mime="image/png", metadata=None, limits=None, intake=None):
    intake = intake or MultimodalIntake()
    asset = intake.sanitize_verified(
        asset_id="actual-source",
        modality=modality,
        mime_type=mime,
        payload=payload,
        metadata=metadata,
        limits=limits,
    )
    return intake, asset


@pytest.mark.parametrize(
    ("format", "mime"), (("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp"))
)
def test_real_decoded_image_binds_source_and_exact_pixels(format, mime):
    payload = _image(format)
    intake, asset = _admit(payload, mime=mime, metadata={"width": 3, "height": 2, "system_prompt": "discard"})
    assert isinstance(asset, VerifiedMultimodalAsset)
    assert asset.validation.source_digest == hashlib.sha256(payload).hexdigest()
    assert asset.validation.format == format
    assert asset.validation.decoded_bytes == 3 * 2 * 4
    with Image.open(io.BytesIO(payload)) as image:
        assert asset.validation.decoded_digest == hashlib.sha256(image.convert("RGBA").tobytes()).hexdigest()
    assert asset.sanitized_metadata["width"] == 3
    assert "system_prompt" not in asset.sanitized_metadata
    assert asset.instruction_trusted is False
    assert verify_verified_asset(asset, payload).digest == asset.digest
    assert intake.verify_verified_asset(asset, payload) == asset
    assert (
        intake.sanitize_verified(
            asset_id="actual-source",
            modality=Modality.IMAGE,
            mime_type=mime,
            payload=payload,
            metadata={"width": 3, "height": 2, "system_prompt": "discard"},
        )
        == asset
    )


@pytest.mark.parametrize("mode", ("1", "L", "P", "RGBA", "I;16"))
def test_png_coding_variants_are_actually_decoded(mode):
    _, asset = _admit(_image(mode=mode))
    assert asset.validation.decoded_bytes == 24
    assert asset.validation.channels == 4


@pytest.mark.parametrize(
    ("channels", "width", "rate"), ((1, 1, 8000), (2, 2, 16000), (1, 3, 22050), (2, 4, 48000))
)
def test_pcm_wave_measures_real_samples_and_duration(channels, width, rate):
    payload = _audio(channels=channels, width=width, rate=rate)
    _, asset = _admit(payload, modality=Modality.AUDIO, mime="audio/wav")
    assert asset.validation.sample_count == 800
    assert asset.validation.channels == channels
    assert asset.validation.sample_width_bytes == width
    assert asset.validation.sample_rate_hz == rate
    assert asset.validation.duration_seconds == 800 / rate
    assert asset.validation.decoded_digest == hashlib.sha256(b"\x01" * 800 * channels * width).hexdigest()
    assert verify_verified_asset(asset, payload) == asset


@pytest.mark.parametrize(
    ("modality", "mime", "payload"),
    (
        (Modality.IMAGE, "image/png", b"png-fixture"),
        (Modality.AUDIO, "audio/wav", b"wav-fixture"),
        (Modality.VIDEO, "video/mp4", b"video-fixture"),
        (Modality.AUDIO, "audio/mpeg", b"compressed-audio"),
    ),
)
def test_opaque_compatibility_assets_do_not_become_decoder_proof(modality, mime, payload):
    intake = MultimodalIntake()
    opaque = intake.sanitize(asset_id="opaque", modality=modality, mime_type=mime, payload=payload)
    with pytest.raises(MultimodalSanitizationError):
        verify_verified_asset(opaque, payload)
    prior = dict(intake._assets)
    with pytest.raises(MultimodalSanitizationError):
        _admit(payload, modality=modality, mime=mime, intake=intake)
    assert intake._assets == prior


@pytest.mark.parametrize(
    "metadata",
    (
        {"width": 2},
        {"height": True},
        {"width": "3"},
        {"format": "JPEG"},
        {"width": float("nan")},
        {"filename": float("inf")},
        {"filename": "x" * 65537},
    ),
)
def test_metadata_conflicts_and_invalid_values_publish_no_asset(metadata):
    intake = MultimodalIntake()
    with pytest.raises(MultimodalSanitizationError):
        _admit(_image(), metadata=metadata, intake=intake)
    assert intake._assets == {}


@pytest.mark.parametrize(
    "metadata",
    (
        {"sample_rate": 16000},
        {"duration_ms": 200},
        {"channels": True},
        {"sample_width_bits": 8},
        {"frame_count": 799},
    ),
)
def test_wave_metadata_must_agree_with_actual_decoded_parameters(metadata):
    intake = MultimodalIntake()
    with pytest.raises(MultimodalSanitizationError, match="conflicts"):
        _admit(_audio(), modality=Modality.AUDIO, mime="audio/wav", metadata=metadata, intake=intake)
    assert intake._assets == {}


@pytest.mark.parametrize(
    "payload",
    (
        _png(tail=b"trailing"),
        _png(decoded=b"\x05\xff\0\0"),
        _png(decoded=b"\0\xff\0"),
        _png(decoded=b"\0" * 1024 * 1024),
        _png(prefix=(_chunk(b"acTL", b"\0" * 8),)),
        _png(prefix=(_chunk(b"EVIL", b"unsupported critical chunk"),)),
    ),
)
def test_png_corruption_and_decoded_bombs_fail_before_publication(payload):
    intake = MultimodalIntake()
    with pytest.raises(MultimodalSanitizationError):
        _admit(payload, intake=intake)
    assert intake._assets == {}


def test_png_crc_and_container_truncation_are_rejected():
    payload = _image()
    for damaged in (payload[:-1], payload[:30] + bytes([payload[30] ^ 1]) + payload[31:]):
        with pytest.raises(MultimodalSanitizationError):
            _admit(damaged)


def test_png_geometry_bomb_is_rejected_before_optional_decoder_allocation(monkeypatch):
    def must_not_decode(*args, **kwargs):
        pytest.fail("unadmitted geometry reached the pixel decoder")

    monkeypatch.setattr(Image, "open", must_not_decode)
    with pytest.raises(MultimodalSanitizationError, match="width"):
        _admit(_png(width=0xFFFFFFFF))


@pytest.mark.parametrize(("format", "mime"), (("JPEG", "image/jpeg"), ("WEBP", "image/webp")))
def test_corrupt_and_mime_disagreeing_real_images_are_rejected(format, mime):
    payload = _image(format)
    for invalid, claimed in ((payload[:-2], mime), (payload, "image/png")):
        with pytest.raises(MultimodalSanitizationError):
            _admit(invalid, mime=claimed)


@pytest.mark.parametrize(
    "change", ("riff_size", "byte_rate", "alignment", "encoding", "truncated", "trailing")
)
def test_wave_container_and_pcm_header_integrity(change):
    payload = bytearray(_audio())
    if change == "riff_size":
        struct.pack_into("<I", payload, 4, 0xFFFFFFFF)
    elif change == "byte_rate":
        struct.pack_into("<I", payload, 28, 1)
    elif change == "alignment":
        struct.pack_into("<H", payload, 32, 1)
    elif change == "encoding":
        struct.pack_into("<H", payload, 20, 3)
    elif change == "truncated":
        del payload[-1]
        struct.pack_into("<I", payload, 4, len(payload) - 8)
    else:
        payload.extend(b"trailing")
    intake = MultimodalIntake()
    with pytest.raises(MultimodalSanitizationError):
        _admit(bytes(payload), modality=Modality.AUDIO, mime="audio/wav", intake=intake)
    assert intake._assets == {}


@pytest.mark.parametrize(
    "limit",
    (
        {"max_pixels": 5},
        {"max_dimension": 2},
        {"max_decoded_bytes": 23},
        {"max_image_bytes": 10},
        {"max_container_chunks": 2},
    ),
)
def test_image_resource_limits_bind_admission_and_receipt(limit):
    with pytest.raises(MultimodalSanitizationError):
        _admit(_image(), limits=MediaValidationLimits(**limit))


@pytest.mark.parametrize(
    "limit",
    (
        {"max_audio_bytes": 10},
        {"max_sample_rate_hz": 7999},
        {"max_audio_channels": 1},
        {"max_decoded_bytes": 3199},
        {"max_audio_seconds": 1},
        {"max_container_chunks": 1},
    ),
)
def test_wave_resource_limits_reject_before_decode(limit):
    with pytest.raises(MultimodalSanitizationError):
        _admit(
            _audio(channels=2, frames=16000),
            modality=Modality.AUDIO,
            mime="audio/wav",
            limits=MediaValidationLimits(**limit),
        )


@pytest.mark.parametrize("value", (True, 0, -1, 1.0, "10", 16_000_001))
def test_invalid_or_expanded_limits_cannot_grant_decoder_authority(value):
    with pytest.raises(MediaValidationError):
        MediaValidationLimits(max_pixels=value)


def test_missing_or_permissive_optional_image_decoder_fails_closed(monkeypatch):
    monkeypatch.setattr(ImageFile, "LOAD_TRUNCATED_IMAGES", True)
    with pytest.raises(MultimodalSanitizationError, match="truncated"):
        _admit(_image())
    monkeypatch.setattr(ImageFile, "LOAD_TRUNCATED_IMAGES", False)
    original_import = builtins.__import__

    def unavailable(name, *args, **kwargs):
        if name == "PIL":
            raise ImportError("optional decoder unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", unavailable)
    with pytest.raises(MultimodalSanitizationError, match="Pillow"):
        _admit(_image())


def test_constructed_or_mutated_receipts_cannot_bypass_payload_verification():
    payload = _image()
    intake, asset = _admit(payload)
    forged = replace(asset, validation=replace(asset.validation, decoded_digest="0" * 64))
    with pytest.raises(MultimodalSanitizationError, match="drift"):
        verify_verified_asset(forged, payload)
    object.__setattr__(asset.validation.limits, "max_pixels", 10**12)
    with pytest.raises(MultimodalSanitizationError, match="max_pixels"):
        intake.verify_verified_asset(asset, payload)


def test_verified_metadata_is_immutable_and_conflicting_reuse_keeps_original():
    payload = _image()
    intake, asset = _admit(payload)
    with pytest.raises(TypeError):
        asset.sanitized_metadata["width"] = 1
    with pytest.raises(MultimodalSanitizationError, match="identity conflict"):
        _admit(_image(size=(2, 2)), intake=intake)
    assert intake._assets[asset.asset_id] is asset
    with pytest.raises(MultimodalSanitizationError):
        verify_verified_asset(asset, _image(size=(2, 2)))


def test_duplicate_wave_chunks_and_oversized_claims_are_bounded():
    payload = _audio()
    duplicate = payload + payload[12:36]
    duplicate = duplicate[:4] + struct.pack("<I", len(duplicate) - 8) + duplicate[8:]
    forged = bytearray(payload)
    struct.pack_into("<I", forged, 40, 0xFFFFFFFF)
    for invalid in (duplicate, bytes(forged)):
        with pytest.raises(MediaValidationError):
            validate_media(invalid, modality="audio", mime_type="audio/wav")


@pytest.mark.parametrize("metadata", ({" width ": 999}, {"width": 3, " width ": 3}))
def test_normalized_metadata_cannot_hide_a_conflicting_measurement(metadata):
    with pytest.raises(MultimodalSanitizationError):
        _admit(_image(), metadata=metadata)


def test_jpeg_end_marker_cannot_hide_trailing_content():
    with pytest.raises(MultimodalSanitizationError, match="trailing"):
        _admit(_image("JPEG") + b"hidden trailing payload\xff\xd9", mime="image/jpeg")


def test_progressive_jpeg_is_fully_decoded_with_bounded_scan_identity():
    output = io.BytesIO()
    with Image.new("RGB", (3, 2), "green") as image:
        image.save(output, format="JPEG", progressive=True)
    _, asset = _admit(output.getvalue(), mime="image/jpeg")
    assert asset.validation.width == 3
    assert asset.validation.height == 2


def test_webp_declared_riff_size_cannot_hide_truncated_trailing_chunks():
    payload = _image("WEBP") + b"JUNK\xff\xff\xff\xff"
    payload = payload[:4] + struct.pack("<I", len(payload) - 8) + payload[8:]
    with pytest.raises(MultimodalSanitizationError, match="truncated"):
        _admit(payload, mime="image/webp")


def test_jpeg_entropy_escaped_bytes_are_samples_rather_than_container_chunks():
    output = io.BytesIO()
    with Image.frombytes("RGB", (512, 512), random.Random(23).randbytes(512 * 512 * 3)) as image:
        image.save(output, format="JPEG")
    payload = output.getvalue()
    assert payload.count(b"\xff\0") > 32
    _, asset = _admit(payload, mime="image/jpeg", limits=MediaValidationLimits(max_container_chunks=32))
    assert asset.validation.decoded_bytes == 512 * 512 * 4
