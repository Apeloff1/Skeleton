"""GF-P1-03, GF-P1-04, and GF-P1-05 temporal world memory."""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from skeleton.frontier_temporal import (
    EXISTING_DIGEST_FIELDS,
    CameraPose,
    ObservationCursor,
    StoredAABB,
    TemporalMemoryError,
    TemporalRecord,
    TemporalWorldMemory,
    decide_frame_policy,
    evaluate_long_horizon_drift,
    evaluate_occlusion,
    evaluate_viewpoint_revisit,
    evaluate_visual_continuity,
    read_existing_digest,
)
from skeleton.jeeves.game_frontier_frame_coherence import FrameChunk, FrameObject, FrameReceipt, digest
from skeleton.jeeves.game_frontier_p1_worldmodel import WorldModelEvidence
from skeleton.jeeves.game_frontier_production import Vec3

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "skeleton" / "frontier_temporal"
DIGEST_A = "ab" * 32
DIGEST_B = "cd" * 32
DIGEST_C = "ef" * 32
DIGEST_D = "12" * 32
DIGEST_E = "34" * 32


def _pose(x: float = 0.0, yaw: float = 0.0) -> CameraPose:
    return CameraPose(x, 0.0, 0.0, yaw, 0.0, 0.0)


def _record(index: int, digest_value: str, action: tuple = ("idle",), x: float = 0.0) -> TemporalRecord:
    return TemporalRecord(
        frame_index=index,
        observation_digest=digest_value,
        observation_digest_field="receipt_digest",
        action=action,
        pose=_pose(x),
    )


def _fill(memory: TemporalWorldMemory, digests: list[str], action: tuple = ("idle",)) -> None:
    for index, digest_value in enumerate(digests):
        memory.append(_record(index, digest_value, action, x=float(index)))


def test_existing_digest_fields_are_referenced_not_rehashed() -> None:
    source = DIGEST_A
    obj = FrameObject("actor-1", Vec3(0, 0, 0), Vec3(0, 0, 0), source)
    partial = FrameChunk(0, (0, 0), (obj,), "")
    chunk = FrameChunk(0, (0, 0), (obj,), digest(partial.payload()))
    receipt = FrameReceipt(
        0, 0, 60, source, None, (chunk,), (), True, True, True, source,
    )
    evidence = WorldModelEvidence(source, 3, 1, DIGEST_B, "adapter")
    assert read_existing_digest(chunk, "content_digest") == chunk.content_digest
    assert read_existing_digest(receipt, "receipt_digest") == receipt.receipt_digest
    assert read_existing_digest(evidence, "source_digest") == evidence.source_digest
    assert read_existing_digest(evidence, "reconstruction_digest") == evidence.reconstruction_digest
    pixel = {"pixel_sha256": DIGEST_C}
    assert read_existing_digest(pixel, "pixel_sha256") == DIGEST_C
    assert "content_digest" in EXISTING_DIGEST_FIELDS
    assert "payload_digest" in EXISTING_DIGEST_FIELDS
    with pytest.raises(TemporalMemoryError):
        read_existing_digest(chunk, "rendered_frame_digest")


def test_append_is_gap_free_and_monotonic() -> None:
    memory = TemporalWorldMemory(4)
    memory.append(_record(0, DIGEST_A))
    with pytest.raises(TemporalMemoryError):
        memory.append(_record(2, DIGEST_B))
    with pytest.raises(TemporalMemoryError):
        memory.append(_record(0, DIGEST_B))
    assert memory.next_frame_index == 1
    assert [item.frame_index for item in memory.live_records] == [0]
    memory.append(_record(1, DIGEST_B))
    assert [item.frame_index for item in memory.live_records] == [0, 1]


def test_capacity_evicts_oldest_and_revisit_compares_summary() -> None:
    memory = TemporalWorldMemory(2)
    memory.append(_record(0, DIGEST_A, ("strafe-left",)))
    memory.append(_record(1, DIGEST_B))
    memory.append(_record(2, DIGEST_C))
    assert [item.frame_index for item in memory.live_records] == [1, 2]
    assert len(memory.live_records) <= memory.capacity
    assert len(memory.summaries) == 1
    assert memory.summaries[0].frame_index == 0
    assert memory.summaries[0].observation_digest == DIGEST_A
    exported = json.dumps(memory.summaries[0].as_dict())
    assert "strafe-left" not in exported
    assert memory.summaries[0].action_digest == _record(0, DIGEST_A, ("strafe-left",)).action_digest
    comparison = memory.compare_revisit(DIGEST_A, _pose(0.0))
    assert comparison.matched is True
    assert comparison.source == "summary"
    assert comparison.distance == 0.0
    moved = memory.compare_revisit(DIGEST_A, _pose(3.0))
    assert moved.matched is True
    assert moved.distance == 3.0
    assert memory.status()["renders_frames"] is False
    assert memory.status()["loads_weights"] is False
    assert memory.status()["model_calls"] == 0


def test_summary_window_is_bounded_and_replay_digest_matches() -> None:
    digests = [DIGEST_A, DIGEST_B, DIGEST_C, DIGEST_D, DIGEST_E]
    actions = ("idle",)

    def replay() -> TemporalWorldMemory:
        memory = TemporalWorldMemory(2)
        for index, digest_value in enumerate(digests):
            memory.append(_record(index, digest_value, actions, x=float(index)))
        return memory

    first = replay()
    second = replay()
    assert len(first.live_records) == 2
    assert len(first.summaries) == 2
    assert first.archive_digest is not None
    assert first.summary_digest == second.summary_digest
    restored = TemporalWorldMemory.from_state(first.export_state())
    assert restored.summary_digest == first.summary_digest
    other = TemporalWorldMemory(2)
    for index, digest_value in enumerate(digests):
        other.append(_record(index, digest_value, ("turn",), x=float(index)))
    assert other.summary_digest != first.summary_digest
    folded = first.compare_revisit(DIGEST_A, _pose(0.0))
    assert folded.matched is False
    retained = first.compare_revisit(DIGEST_C, _pose(2.0))
    assert retained.matched is True
    assert retained.source == "summary"


def test_checkpoint_reject_does_not_mutate_memory() -> None:
    memory = TemporalWorldMemory(2)
    _fill(memory, [DIGEST_A, DIGEST_B, DIGEST_C])
    original = memory.summary_digest
    state = memory.export_state()
    state["summaries"][0]["summary_digest"] = DIGEST_D
    with pytest.raises(TemporalMemoryError):
        memory.restore(state)
    assert memory.summary_digest == original


def test_visual_continuity_is_the_repeated_fraction() -> None:
    before = [DIGEST_A, DIGEST_B, DIGEST_A]
    after = [DIGEST_A, DIGEST_C, DIGEST_A, DIGEST_A]
    first = evaluate_visual_continuity(before, after, bound=0.75)
    second = evaluate_visual_continuity(before, after, bound=0.75)
    assert first == second
    assert first.measured == 0.75
    assert first.passed is True
    assert first.comparison == "gte"
    failed = evaluate_visual_continuity(before, after, bound=0.8)
    assert failed.measured == 0.75
    assert failed.passed is False
    with pytest.raises(TemporalMemoryError):
        evaluate_visual_continuity(before, [], bound=0.0)


def test_occlusion_ray_against_stored_aabbs() -> None:
    camera = _pose(0.0)
    subject = (10.0, 0.0, 0.0)
    blocking = StoredAABB(5.0, -1.0, -1.0, 6.0, 1.0, 1.0)
    closer = StoredAABB(2.5, -1.0, -1.0, 3.0, 1.0, 1.0)
    beside = StoredAABB(4.0, 2.0, -1.0, 6.0, 3.0, 1.0)
    behind = StoredAABB(-6.0, -1.0, -1.0, -4.0, 1.0, 1.0)
    at_subject = StoredAABB(10.0, -1.0, -1.0, 11.0, 1.0, 1.0)
    clear = evaluate_occlusion(camera, subject, [beside, behind, at_subject], bound=1.0)
    hit = evaluate_occlusion(camera, subject, [blocking, closer], bound=0.25)
    again = evaluate_occlusion(camera, subject, [blocking, closer], bound=0.25)
    assert clear.measured == 1.0 and clear.passed is True
    assert hit == again
    assert hit.measured == 0.25
    assert hit.passed is True
    assert evaluate_occlusion(camera, subject, [blocking], bound=0.75).passed is False
    inside = evaluate_occlusion(_pose(5.0), subject, [blocking], bound=0.0)
    assert inside.measured == 0.0 and inside.passed is True
    with pytest.raises(TemporalMemoryError):
        evaluate_occlusion(camera, (0.0, 0.0, 0.0), [], bound=1.0)


def test_viewpoint_revisit_and_long_horizon_drift() -> None:
    stored = _pose(1.0, yaw=0.25)
    same = evaluate_viewpoint_revisit(stored, stored, bound=0.0)
    near = evaluate_viewpoint_revisit(_pose(1.0, yaw=0.25), stored, bound=0.1)
    far = evaluate_viewpoint_revisit(_pose(4.0, yaw=0.25), stored, bound=0.5)
    wrapped = evaluate_viewpoint_revisit(_pose(1.0, yaw=3.141592653589793), _pose(1.0, yaw=-3.141592653589793), bound=1e-9)
    assert same.measured == near.measured == 0.0
    assert same.passed is True and same.comparison == "lte"
    assert far.measured == 3.0 and far.passed is False
    assert wrapped.measured == pytest.approx(0.0) and wrapped.passed is True
    estimated = [_pose(0.0), _pose(0.5), _pose(1.0)]
    truth = [_pose(0.0), _pose(0.0), _pose(0.0)]
    drift = evaluate_long_horizon_drift(estimated, truth, bound=1.0)
    again = evaluate_long_horizon_drift(estimated, truth, bound=1.0)
    assert drift == again
    assert drift.measured == 1.0 and drift.passed is True
    assert evaluate_long_horizon_drift(estimated, truth, bound=0.5).passed is False
    shrinking = evaluate_long_horizon_drift([_pose(2.0), _pose(0.0)], [_pose(0.0), _pose(0.0)], bound=0.0)
    assert shrinking.measured == -2.0 and shrinking.passed is True
    with pytest.raises(TemporalMemoryError):
        evaluate_long_horizon_drift(estimated, truth[:-1], bound=1.0)


def test_frame_policy_is_pure_for_every_target_rate() -> None:
    for rate in (30, 50, 60, 120):
        present = decide_frame_policy(
            target_rate=rate, simulation_step_s=1.0 / rate, fixed_dt_s=1.0 / rate,
        )
        again = decide_frame_policy(
            target_rate=rate, simulation_step_s=1.0 / rate, fixed_dt_s=1.0 / rate,
        )
        interpolated = decide_frame_policy(
            target_rate=rate, simulation_step_s=1.5 / rate, fixed_dt_s=1.0 / rate,
        )
        coarse = decide_frame_policy(
            target_rate=rate, simulation_step_s=0.5 / rate, fixed_dt_s=2.0 / rate,
        )
        dropped = decide_frame_policy(
            target_rate=rate, simulation_step_s=3.0 / rate, fixed_dt_s=1.0 / rate,
        )
        assert present == again
        assert present.decision == "present"
        assert present.label == "captured"
        assert present.advances_observation_index is True
        assert present.storable_as_captured is True
        assert interpolated.decision == "interpolate"
        assert interpolated.label == "interpolated"
        assert interpolated.interpolation_alpha == 0.5
        assert interpolated.storable_as_captured is False
        assert interpolated.advances_observation_index is False
        assert coarse.decision == "interpolate"
        assert coarse.interpolation_alpha == 0.25
        assert dropped.decision == "drop"
        assert dropped.label == "dropped"
        assert dropped.advances_observation_index is False
        assert dropped.storable_as_captured is False
    with pytest.raises(TemporalMemoryError):
        decide_frame_policy(target_rate=24, simulation_step_s=1 / 24, fixed_dt_s=1 / 24)
    with pytest.raises(TemporalMemoryError):
        decide_frame_policy(target_rate=60, simulation_step_s=0.0, fixed_dt_s=0.0)


def test_drop_does_not_advance_and_interpolation_is_not_stored() -> None:
    memory = TemporalWorldMemory(4)
    cursor = ObservationCursor(memory)
    with pytest.raises(TemporalMemoryError):
        TemporalRecord(0, DIGEST_A, "receipt_digest", ("idle",), _pose(), kind="interpolated")
    drop = decide_frame_policy(target_rate=60, simulation_step_s=3 / 60, fixed_dt_s=1 / 60)
    blend = decide_frame_policy(target_rate=60, simulation_step_s=1.5 / 60, fixed_dt_s=1 / 60)
    show = decide_frame_policy(target_rate=60, simulation_step_s=1 / 60, fixed_dt_s=1 / 60)
    assert cursor.apply(
        drop, observation_digest=DIGEST_A, observation_digest_field="receipt_digest",
        action=("idle",), pose=_pose(),
    )["label"] == "dropped"
    assert cursor.apply(
        blend, observation_digest=DIGEST_B, observation_digest_field="content_digest",
        action=("idle",), pose=_pose(),
    )["label"] == "interpolated"
    stored = cursor.apply(
        show, observation_digest=DIGEST_C, observation_digest_field="pixel_sha256",
        action=("move", 1), pose=_pose(1.0),
    )
    assert stored["stored"] is True
    assert stored["observation_index"] == 0
    assert cursor.observation_index == 1
    assert [item.frame_index for item in memory.live_records] == [0]
    assert memory.live_records[0].kind == "captured"
    assert cursor.metrics() == {
        "observation_index": 1,
        "presented": 1,
        "interpolated": 1,
        "dropped": 1,
        "stored_observations": 1,
    }


def test_package_has_no_clock_randomness_or_provider_sdk() -> None:
    banned = {
        "time", "datetime", "random", "secrets", "uuid",
        "openai", "anthropic", "torch", "tensorflow", "transformers",
    }
    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [(node.module or "").split(".")[0]]
            else:
                if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
                    func = node.exc.func
                    if isinstance(func, ast.Name):
                        assert func.id != "NotImplementedError"
                continue
            assert banned.isdisjoint(names)
        source = path.read_text(encoding="utf-8")
        assert "NotImplemented" not in source
        assert "renders a frame" not in source.lower()
        assert "gpu playback" not in source.lower()
