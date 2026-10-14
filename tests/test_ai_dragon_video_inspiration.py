"""Video Dragon indexes only consent-gated predecoded, source-bound observations."""
from dataclasses import replace
import pytest

from skeleton.ai.webcrawler.dragon_frame_custody import CapturedFrame, FrameBatch
from skeleton.ai.webcrawler.dragon_temporal_segmentation import FeatureFrame
from skeleton.ai.webcrawler.dragon_visual_features import VisualFeatureBatch
from skeleton.ai.webcrawler.video_digest import VideoKnowledgeChunk, VideoObservation
from skeleton.ai.webcrawler.dragon_video_inspiration import digest_video_inspiration

URL = "https://examples.invalid/reviewed-clip"
SOURCE = "source-" + "a" * 64
FRAME = "frame-001"


def _input():
    custody = FrameBatch(
        (
            CapturedFrame(
                FRAME, "owner", "job", "b" * 64,
                "consent-1", "c" * 64, 1000, "d" * 64, 2000,
                "frame://frame-001",
            ),
        ),
        "e" * 64,
    )
    visuals = VisualFeatureBatch(
        (FeatureFrame(1000, (0.3, 0.7), FRAME),),
        "f" * 64,
        custody.batch_fingerprint,
    )
    transcript = (
        VideoKnowledgeChunk(
            "chunk-1", 0, 1800, "shader workflow",
            ("transcript",), ("obs-1",), URL,
        ),
    )
    observation = VideoObservation(
        900, 1100, "frame_description",
        "Godot shader lighting and tilemap walkthrough", 0.9, FRAME,
    )
    return custody, visuals, transcript, (observation,)


def _run(**changes):
    custody, visuals, transcript, observations = _input()
    args = dict(
        source_id=SOURCE, source_url=URL, transcript=transcript,
        decoded_visual=visuals, descriptions=observations,
        source_frames=custody, consent_verified=True, authorized=True,
    )
    args.update(changes)
    return digest_video_inspiration(**args)


def test_visual_bookmark_is_timecoded_and_only_inspiration() -> None:
    report = _run()
    assert report["bookmarked_clips"] == 1
    assert report["tool_editor_leads"] == ["godot", "lighting", "shader", "tilemap"]
    assert len(report["bookmark_digest"]) == 64
    note = report["notes"][0]
    assert note["frame_digest"] == "d" * 64
    assert note["start_ms"] == 900 and note["end_ms"] == 1100
    assert note["visual_feature_fingerprint"] == "f" * 64
    assert note["reviewer_required"]
    assert report["independent_visual_fact_review_required"]
    assert report["normal_weight_promotion_authorized"] is False
    assert report["hyperweight_promotion_authorized"] is False
    assert report["neural_training_authorized"] is False
    assert report["network_requests"] == 0
    assert report == _run()


@pytest.mark.parametrize("kwargs", [
    {"authorized": False},
    {"consent_verified": False},
    {"consent_verified": None},
])
def test_video_inspiration_refuses_unauthorized_or_unverified_capture(kwargs) -> None:
    with pytest.raises(PermissionError):
        _run(**kwargs)


def test_forged_frame_binding_and_unaligned_transcript_are_rejected() -> None:
    custody, visuals, transcript, observations = _input()
    with pytest.raises(ValueError, match="bound"):
        _run(decoded_visual=replace(visuals, source_batch_fingerprint="f" * 64))
    with pytest.raises(ValueError, match="captured frame"):
        _run(descriptions=(replace(observations[0], source_id="made-up"),))
    with pytest.raises(ValueError, match="timecode"):
        _run(transcript=(replace(transcript[0], start_ms=4000, end_ms=5000),))
    with pytest.raises(ValueError, match="identity"):
        _run(transcript=(replace(transcript[0], source_url="https://other.invalid/"),))


def test_bad_source_mime_and_duplicate_observations_fail_closed() -> None:
    _, _, _, observations = _input()
    with pytest.raises(ValueError, match="canonical video source"):
        _run(source_url="https://")
    with pytest.raises(ValueError, match="bounded canonical"):
        _run(max_notes=True)
    with pytest.raises(ValueError, match="duplicate"):
        _run(descriptions=observations + observations, max_notes=2)
    with pytest.raises(ValueError, match="visually"):
        _run(descriptions=(replace(observations[0], modality="transcript"),))
    with pytest.raises(ValueError, match="bounded canonical"):
        _run(descriptions=())


def test_low_confidence_visual_observation_stays_unverified() -> None:
    _, _, _, observations = _input()
    report = _run(descriptions=(replace(observations[0], confidence=0.3),))
    assert report["notes"][0]["note"].startswith("(Unverified visual description; inspection required)")
    assert report["notes"][0]["reviewer_required"]
