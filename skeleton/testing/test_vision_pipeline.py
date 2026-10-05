from __future__ import annotations

import hashlib

import pytest

from skeleton.vision.pipeline import ImageAsset, ImageLimits, ImageRegion, VisionError, VisionResult


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def asset(**changes: object) -> ImageAsset:
    values = dict(
        asset_id="IMAGE.1",
        source_digest=sha("source"),
        format="png",
        width=100,
        height=80,
        encoded_bytes=1000,
    )
    values.update(changes)
    return ImageAsset(**values)


def region(**changes: object) -> ImageRegion:
    values = dict(
        asset_id="IMAGE.1",
        x=10,
        y=20,
        width=30,
        height=40,
        transform_digest=sha("crop"),
    )
    values.update(changes)
    return ImageRegion(**values)


def result(**changes: object) -> VisionResult:
    values = dict(
        region=region(),
        asset=asset(),
        model_digest=sha("model"),
        confidence=0.75,
        payload_digest=sha("payload"),
    )
    values.update(changes)
    return VisionResult.create(**values)


def test_decode_limits_checked_before_processing() -> None:
    assert ImageLimits(200, 200, 20_000, 2_000).admit(asset())


def test_decompression_bomb_dimensions_rejected() -> None:
    with pytest.raises(VisionError, match="decode limits"):
        ImageLimits(200, 200, 20_000, 2_000).admit(asset(width=10_000))


def test_limit_policy_itself_is_bounded_and_typed() -> None:
    with pytest.raises(VisionError, match="max_pixels outside safety bound"):
        ImageLimits(200, 200, 10**30, 2_000)
    with pytest.raises(VisionError, match="max_width outside safety bound"):
        ImageLimits(True, 200, 20_000, 2_000)


def test_asset_rejects_type_confusion_and_unknown_format() -> None:
    with pytest.raises(VisionError, match="width outside safety bound"):
        asset(width=True)
    with pytest.raises(VisionError, match="unsupported image format"):
        asset(format="svg")


def test_region_preserves_source_coordinates_and_transform() -> None:
    assert region().validate(asset())


def test_region_coordinate_drift_outside_source_rejected() -> None:
    with pytest.raises(VisionError, match="outside"):
        region(x=90).validate(asset())


def test_region_rejects_boolean_coordinate_confusion() -> None:
    with pytest.raises(VisionError, match="origin"):
        region(x=False)


def test_result_binds_source_region_model_confidence_and_payload() -> None:
    original = result()
    assert len(original.result_digest) == 64
    changed = result(model_digest=sha("different-model"))
    assert changed.result_digest != original.result_digest
    changed = result(payload_digest=sha("different-payload"))
    assert changed.result_digest != original.result_digest
    changed = result(region=region(transform_digest=sha("rotate")))
    assert changed.result_digest != original.result_digest


def test_result_rejects_source_substitution() -> None:
    with pytest.raises(VisionError, match="outside source image"):
        VisionResult.create(region(), asset(asset_id="IMAGE.2"), sha("model"), 0.5, sha("payload"))


def test_nonfinite_confidence_rejected() -> None:
    with pytest.raises(VisionError, match="confidence"):
        result(confidence=float("nan"))


def test_forged_result_digest_is_rejected() -> None:
    valid = result()
    with pytest.raises(VisionError, match="exact provenance"):
        VisionResult(
            valid.region,
            valid.source_digest,
            valid.model_digest,
            valid.confidence,
            valid.payload_digest,
            sha("forged"),
        )
