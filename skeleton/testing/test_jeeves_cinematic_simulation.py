"""Bounded cinematic rehearsal, reverse data audit and multi-sim contracts.

These tests exercise real deterministic camera frames and receipts, but make
no claim of rendering, cloth dynamics, or model weight improvements.
"""
from __future__ import annotations

from copy import deepcopy
import pytest

from skeleton.ai.training.jeeves_cinematic_simulation import (
    CinematicSimError, SimulationController, validate_scene, variation_controls,
    simulate_once, run_batch, verify_batch_report, MAX_BATCH_FRAMES,
)


def scene():
    def camera(mode, start, end, aim_start, aim_end):
        return {
            "mode": mode, "from_mm": start, "to_mm": end,
            "look_from_mm": aim_start, "look_to_mm": aim_end,
            "fov_start_deg": 55, "fov_end_deg": 48,
        }
    return {
        "schema_version": "skeleton.jeeves.cinematic_sim.v1",
        "source_project_id": "original_quest", "scene_id": "chapter_one",
        "rights_reviewed": True,
        "actors": [{
            "id": "hero", "voice_id": "voice_hero", "appearance_id": "face_hero",
            "strength_g": 2000, "allowed_apparel": ["cloak", "armor"],
        }],
        "items": [{"id": "lantern", "mass_g": 1500}],
        "apparel": [
            {"id": "cloak", "drag_pct": 12, "mobility_pct": 95},
            {"id": "armor", "drag_pct": 25, "mobility_pct": 35},
        ],
        "dialogue": [{"id": "line_one", "actor_id": "hero"},
                     {"id": "line_two", "actor_id": "hero"}],
        "shots": [
            {
                "id": "opening", "start_ms": 0, "duration_ms": 800,
                "camera": camera("establishing", [0, 0, 1200], [200, 0, 1200],
                                 [5000, 0, 1300], [5000, 300, 1300]),
                "axis": "axis_a", "transition": "straight", "actor_id": "hero",
                "voice_id": "voice_hero", "dialogue_ids": [],
                "item_id": "", "apparel_id": "cloak", "lighting_id": "dawn",
            },
            {
                "id": "reveal", "start_ms": 800, "duration_ms": 900,
                "camera": camera("pan_to", [300, 0, 1300], [350, 500, 1300],
                                 [4500, 0, 1400], [4300, 900, 1400]),
                "axis": "axis_a", "transition": "match_cut", "actor_id": "hero",
                "voice_id": "voice_hero", "dialogue_ids": ["line_one"],
                "item_id": "lantern", "apparel_id": "cloak", "lighting_id": "dawn",
            },
            {
                "id": "handoff", "start_ms": 1700, "duration_ms": 1000,
                "camera": camera("dolly", [400, 300, 1200], [700, 300, 1250],
                                 [5000, 300, 1500], [5000, 650, 1600]),
                "axis": "axis_a", "transition": "continuous", "actor_id": "hero",
                "voice_id": "voice_hero", "dialogue_ids": ["line_two"],
                "item_id": "lantern", "apparel_id": "armor", "lighting_id": "interior",
            },
        ],
    }


def controls(**overrides):
    value = variation_controls()[0]
    return {**value, **overrides}


def test_original_cinematic_source_and_pan_to_validation():
    evidence = validate_scene(scene())
    assert evidence["shot_count"] == 3
    assert evidence["dialogue_count"] == 2
    assert evidence["total_ms"] == 2700
    assert not evidence["rendered_video_verified"]


def test_real_forward_camera_motion_and_no_restart_reverse_audit():
    controller = SimulationController(scene(), controls())
    trace = controller.run()
    assert len(trace) == 28
    pans = [entry for entry in trace if entry["shot"] == "reveal"]
    assert len(pans) >= 8 and len({r["yaw_deg"] for r in pans}) > 2
    assert len({r["camera_mm"] for r in pans}) > 2
    receipt = controller.reverse_audit()
    assert receipt["passed"] and receipt["no_simulation_restart"]
    assert receipt["independent_training_examples_added"] == 0


def test_resume_and_seek_use_one_sim_and_same_evidence_chain():
    first = SimulationController(scene(), controls())
    for _ in range(8):
        first.step()
    first.pause()
    assert first.step() is None
    first.seek(4)
    first.resume()
    restored = first.run()
    original = SimulationController(scene(), controls()).run()
    assert restored == original
    assert first.reverse_audit()["passed"]


def test_reverse_audit_detects_corrupted_observation_without_replay():
    controller = SimulationController(scene(), controls())
    controller.run()
    controller.trace[8]["yaw_deg"] += 25
    verdict = controller.reverse_audit()
    assert not verdict["passed"] and verdict["failures"] > 0


def test_canon_and_apparel_and_item_safety_checks():
    forged = deepcopy(scene())
    forged["shots"][1]["voice_id"] = "imposter"
    with pytest.raises(CinematicSimError, match="voice"):
        validate_scene(forged)
    forged = deepcopy(scene())
    forged["shots"][1]["axis"] = "axis_b"
    with pytest.raises(CinematicSimError, match="screen-axis"):
        validate_scene(forged)
    report = simulate_once(scene(), controls(item_mass_delta_g=750,
                                              apparel_drag_delta_pct=30))
    assert report["audit"]["forward"]["issues"]["item_exceeds_actor_capacity"] > 0
    assert report["audit"]["forward"]["issues"]["apparel_prevents_required_motion"] > 0
    assert report["audit"]["reverse"]["passed"]


def test_multi_sim_perturbation_variants_and_duplicate_evidence_accounting():
    variants = variation_controls(
        offsets=(-20, 0, 20), pan_rates=(75, 100),
        lens_offsets=(-5, 0, 5), item_mass_deltas=(0, 750),
        apparel_drag_deltas=(0, 25), seeds=(0, 1), limit=48)
    assert len(variants) == 48
    summary = run_batch(scene(), variations=variants, workers=1)
    assert summary["simulations_executed"] == 48
    assert summary["forward_observations"] == 48 * 28
    assert summary["forward_observations"] == summary["reverse_observations"]
    assert summary["independent_sgd_exposures"] == 0
    assert summary["candidate_status"] == "quarantined_pending_independent_review"
    assert verify_batch_report(summary)["reverse_audit_verified"]
    identical_seed_variants = variation_controls(seeds=(1, 2), limit=2)
    duplicate = run_batch(scene(), variations=identical_seed_variants)
    assert duplicate["unique_trace_digests"] == 1
    assert duplicate["duplicates_not_counted_as_new_training"] == 1


def test_report_tamper_and_invalid_multi_sim_limits_fail_closed():
    report = run_batch(scene(), variations=variation_controls())
    tamper = deepcopy(report)
    tamper["simulators"][0]["frames_executed"] = 500
    with pytest.raises(CinematicSimError, match="receipt"):
        verify_batch_report(tamper)
    with pytest.raises(CinematicSimError, match="duplicate"):
        run_batch(scene(), variations=(controls(), controls()))
    # A 120-second scene at high sampling density crosses the hard batch budget.
    many = deepcopy(scene())
    many["shots"][-1]["duration_ms"] = 28000
    many["shots"][-1]["start_ms"] = 1700
    with pytest.raises(CinematicSimError, match="budget"):
        run_batch(many, variations=variation_controls(
            offsets=(-20, 0, 20), pan_rates=(75, 100), lens_offsets=(-5, 0, 5),
            item_mass_deltas=(0, 750), apparel_drag_deltas=(0, 25),
            seeds=(0, 1), limit=48), frame_ms=25)
