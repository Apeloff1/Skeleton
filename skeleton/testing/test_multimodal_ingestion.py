from __future__ import annotations

import hashlib

import pytest

from skeleton.ai.runtime.extensions.multimodal import MediaTransform, ResourceLimits
from skeleton.artifacts.multimodal_ingestion import (
    IngestionError,
    IngestionPolicy,
    MediaProbe,
    MultimodalIngestionCore,
    PipelineBinding,
)


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def policy(**limits: object) -> IngestionPolicy:
    resource_limits = ResourceLimits(
        max_bytes=int(limits.get("max_bytes", 1024)),
        max_pixels=int(limits.get("max_pixels", 1_000_000)),
        max_audio_seconds=float(limits.get("max_audio_seconds", 60)),
        max_video_seconds=float(limits.get("max_video_seconds", 60)),
        max_frames=int(limits.get("max_frames", 1_800)),
    )
    return IngestionPolicy(
        policy_id="MM.INGEST.V1",
        allowed_media_types=frozenset({"image", "audio", "video"}),
        allowed_trust_labels=frozenset({"trusted", "untrusted"}),
        allowed_classifications=frozenset({"public", "internal"}),
        metadata_allowlist=frozenset({"title", "language"}),
        limits=resource_limits,
        max_metadata_value_chars=64,
    )


def core(**limits: object) -> MultimodalIngestionCore:
    return MultimodalIngestionCore(
        policy(**limits),
        (
            PipelineBinding("image", "PIPE.IMAGE.V1", frozenset({"png", "jpeg"})),
            PipelineBinding("audio", "PIPE.AUDIO.V1", frozenset({"wav"})),
            PipelineBinding("video", "PIPE.VIDEO.V1", frozenset({"mp4"})),
        ),
    )


def test_admission_binds_source_policy_metadata_and_pipeline_before_decode() -> None:
    runtime = core()
    payload = b"image-bytes"
    probe = MediaProbe(
        media_type="image",
        format="png",
        byte_size=len(payload),
        width=640,
        height=480,
        metadata={"title": "diagram", "language": "en"},
    )

    asset, receipt = runtime.admit_predecode(
        payload,
        probe,
        trust_label="untrusted",
        classification="internal",
    )

    assert asset.source_digest == hashlib.sha256(payload).hexdigest()
    assert asset.byte_size == len(payload)
    assert asset.metadata["safe_metadata"] == {"title": "diagram", "language": "en"}
    assert receipt.asset_digest == asset.digest
    assert receipt.pipeline_id == "PIPE.IMAGE.V1"
    assert receipt.policy_digest == runtime.policy.digest
    assert runtime.asset_for_source(asset.source_digest) == asset


def test_trust_and_classification_fail_closed_before_registration() -> None:
    runtime = core()
    payload = b"image"
    probe = MediaProbe("image", "png", len(payload), width=4, height=4)

    with pytest.raises(IngestionError, match="trust label"):
        runtime.admit_predecode(
            payload,
            probe,
            trust_label="quarantined",
            classification="public",
        )
    with pytest.raises(IngestionError, match="classification"):
        runtime.admit_predecode(
            payload,
            probe,
            trust_label="trusted",
            classification="secret",
        )
    with pytest.raises(KeyError):
        runtime.asset_for_source(hashlib.sha256(payload).hexdigest())


def test_declared_size_and_resource_bombs_are_rejected_predecode() -> None:
    payload = b"x" * 10
    with pytest.raises(IngestionError, match="declared byte_size"):
        core().admit_predecode(
            payload,
            MediaProbe("image", "png", 9, width=1, height=1),
            trust_label="trusted",
            classification="public",
        )
    with pytest.raises(IngestionError, match="byte limit"):
        core(max_bytes=5).admit_predecode(
            payload,
            MediaProbe("image", "png", len(payload), width=1, height=1),
            trust_label="trusted",
            classification="public",
        )
    with pytest.raises(IngestionError, match="pixel limit"):
        core(max_pixels=99).admit_predecode(
            b"img",
            MediaProbe("image", "png", 3, width=10, height=10),
            trust_label="trusted",
            classification="public",
        )
    with pytest.raises(IngestionError, match="frame budget"):
        core(max_frames=20).admit_predecode(
            b"vid",
            MediaProbe(
                "video",
                "mp4",
                3,
                width=10,
                height=10,
                duration_seconds=2,
                fps=30,
            ),
            trust_label="trusted",
            classification="public",
        )


def test_audio_and_video_require_resource_facts_before_decode() -> None:
    runtime = core()
    with pytest.raises(IngestionError, match="audio duration"):
        runtime.admit_predecode(
            b"aud",
            MediaProbe("audio", "wav", 3),
            trust_label="trusted",
            classification="public",
        )
    with pytest.raises(IngestionError, match="video duration and fps"):
        runtime.admit_predecode(
            b"vid",
            MediaProbe("video", "mp4", 3, width=4, height=4),
            trust_label="trusted",
            classification="public",
        )


def test_metadata_is_allowlisted_not_silently_dropped() -> None:
    runtime = core()
    with pytest.raises(IngestionError, match="not allowed"):
        runtime.admit_predecode(
            b"img",
            MediaProbe(
                "image",
                "png",
                3,
                width=1,
                height=1,
                metadata={"gps": "60.3913,5.3221"},
            ),
            trust_label="untrusted",
            classification="public",
        )
    with pytest.raises(IngestionError, match="exceeds size limit"):
        runtime.admit_predecode(
            b"img",
            MediaProbe(
                "image",
                "png",
                3,
                width=1,
                height=1,
                metadata={"title": "x" * 65},
            ),
            trust_label="untrusted",
            classification="public",
        )


def test_format_must_match_registered_modality_pipeline() -> None:
    runtime = core()
    with pytest.raises(IngestionError, match="format is not accepted"):
        runtime.admit_predecode(
            b"img",
            MediaProbe("image", "gif", 3, width=1, height=1),
            trust_label="trusted",
            classification="public",
        )


def test_transform_lineage_is_append_only_and_modality_bound() -> None:
    runtime = core()
    payload = b"image"
    asset, _ = runtime.admit_predecode(
        payload,
        MediaProbe("image", "png", len(payload), width=4, height=4),
        trust_label="trusted",
        classification="public",
    )
    first = MediaTransform(
        "TRANSFORM.RESIZE",
        asset.source_digest,
        sha("resized"),
        "image",
        {"width": 2, "height": 2},
    )
    second = MediaTransform(
        "TRANSFORM.NORMALIZE",
        first.output_digest,
        sha("normalized"),
        "image",
        {"space": "srgb"},
    )
    runtime.record_transform(first)
    runtime.record_transform(second)
    assert runtime.lineage(second.output_digest) == (first, second)

    with pytest.raises(IngestionError, match="not admitted"):
        runtime.record_transform(
            MediaTransform(
                "TRANSFORM.ORPHAN",
                sha("unknown"),
                sha("orphan"),
                "image",
            )
        )
    with pytest.raises(IngestionError, match="modality"):
        runtime.record_transform(
            MediaTransform(
                "TRANSFORM.WRONG.MODALITY",
                second.output_digest,
                sha("wrong"),
                "audio",
            )
        )
    with pytest.raises(IngestionError, match="already registered"):
        runtime.record_transform(
            MediaTransform(
                "TRANSFORM.REUSE.OUTPUT",
                second.output_digest,
                first.output_digest,
                "image",
            )
        )


def test_same_content_cannot_be_readmitted_under_different_authority_metadata() -> None:
    runtime = core()
    payload = b"same"
    probe = MediaProbe("image", "png", len(payload), width=2, height=2)
    runtime.admit_predecode(
        payload,
        probe,
        trust_label="trusted",
        classification="public",
    )
    with pytest.raises(IngestionError, match="different metadata"):
        runtime.admit_predecode(
            payload,
            probe,
            trust_label="untrusted",
            classification="public",
        )


def test_policy_digest_is_order_independent() -> None:
    left = IngestionPolicy(
        "MM.INGEST.V1",
        frozenset({"video", "image", "audio"}),
        frozenset({"untrusted", "trusted"}),
        frozenset({"internal", "public"}),
        frozenset({"language", "title"}),
        ResourceLimits(
            max_bytes=10,
            max_pixels=20,
            max_audio_seconds=30,
            max_video_seconds=40,
            max_frames=50,
        ),
    )
    right = IngestionPolicy(
        "MM.INGEST.V1",
        frozenset({"audio", "image", "video"}),
        frozenset({"trusted", "untrusted"}),
        frozenset({"public", "internal"}),
        frozenset({"title", "language"}),
        ResourceLimits(
            max_bytes=10,
            max_pixels=20,
            max_audio_seconds=30,
            max_video_seconds=40,
            max_frames=50,
        ),
    )
    assert left.digest == right.digest
