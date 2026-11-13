"""GF-A runtime binding: candidate -> authorised Jeeves/Forge/Godot runtime."""
from __future__ import annotations

from dataclasses import replace
import json

import pytest

from skeleton.jeeves.game_frontier_runtime_binding import (
    RuntimeBindingError, authorise_candidate, bind_scene_candidate,
    binding_ui_status, digest_of, era_profile, route_runtime_outputs,
)
from tests.test_game_frontier_godot import source_scene

KEY = b"operator-key-0123456789"


@pytest.fixture(scope="module")
def candidate():
    return source_scene()


def _auth(candidate, **kw):
    args = dict(operator_id="ops", era="early_3d", issued_ms=1000,
                ttl_ms=60_000, key=KEY)
    args.update(kw)
    return authorise_candidate(candidate.manifest_digest, **args)


def test_binds_real_candidate_through_godot_emitter(candidate):
    binding = bind_scene_candidate(candidate, _auth(candidate), key=KEY, now_ms=2000)
    assert binding.candidate_digest == candidate.manifest_digest
    assert binding.era == "early_3d" and binding.fps == 120
    assert "frontier/frontier_scene.tscn" in binding.godot_files
    data = json.loads(binding.godot_files["frontier/data/runtime_binding.json"])
    assert data["candidate"] == candidate.manifest_digest
    assert candidate.approved_for_runtime is False
    status = binding_ui_status(binding)
    assert status["claim"] == "bound_pending_native_render_qa"
    assert status["binding_id"] == binding.binding_id


def test_binding_is_deterministic(candidate):
    a = bind_scene_candidate(candidate, _auth(candidate), key=KEY, now_ms=2000)
    b = bind_scene_candidate(candidate, _auth(candidate), key=KEY, now_ms=2000)
    assert a.binding_id == b.binding_id


def test_rejects_wrong_key(candidate):
    with pytest.raises(RuntimeBindingError, match="signature"):
        bind_scene_candidate(candidate, _auth(candidate), key=b"x" * 20, now_ms=2000)


def test_rejects_expired_and_early(candidate):
    auth = _auth(candidate)
    for now in (999, 61_000):
        with pytest.raises(RuntimeBindingError, match="not valid"):
            bind_scene_candidate(candidate, auth, key=KEY, now_ms=now)


def test_rejects_tampered_manifest(candidate):
    manifest = dict(candidate.manifest, simulation_time_s=999)
    forged = replace(candidate, manifest=manifest)
    with pytest.raises(RuntimeBindingError, match="digest mismatch"):
        bind_scene_candidate(forged, _auth(candidate), key=KEY, now_ms=2000)


def test_rejects_self_approved_candidate(candidate):
    with pytest.raises(RuntimeBindingError, match="unadmitted"):
        bind_scene_candidate(replace(candidate, approved_for_runtime=True),
                             _auth(candidate), key=KEY, now_ms=2000)


def test_rejects_era_mismatch(candidate):
    with pytest.raises(RuntimeBindingError, match="era"):
        bind_scene_candidate(candidate, _auth(candidate, era="modern_3d"),
                             key=KEY, now_ms=2000)


def test_rejects_auth_for_other_candidate(candidate):
    auth = authorise_candidate("e" * 64, operator_id="ops", era="early_3d",
                               issued_ms=1000, ttl_ms=60_000, key=KEY)
    with pytest.raises(RuntimeBindingError, match="different candidate"):
        bind_scene_candidate(candidate, auth, key=KEY, now_ms=2000)


def test_short_key_refused(candidate):
    with pytest.raises(RuntimeBindingError, match="16 bytes"):
        _auth(candidate, key=b"short")


def test_unknown_era_refused():
    with pytest.raises(RuntimeBindingError):
        era_profile("vr_9000")


MANIFEST = {
    "soft_material_motion": [{"id": "cape", "material": "wool", "xyz": [0, 1, 0],
                              "wetness": .2, "temperature_c": 10}],
    "weather_physics": {"temperature_c": 4, "wind_xyz": [1, 0, 0], "rain_mm_h": 3,
                        "water_depth_m": 0, "snow_depth_m": 0},
    "structures": [{"id": "hut", "material": "timber", "built": True, "age_days": 30,
                    "integrity": .9, "weathering": .1, "maintenance_debt": .0}],
    "character_physics": {"position": [0, 0, 0], "velocity": [1, 0, 0], "traction": .7,
                          "impacts": [{"surface": "rock", "impulse_ns": 3.0,
                                       "damage": 0.1, "material": "granite"}]},
}


def test_routes_all_four_channels_in_3d():
    outputs, dropped = route_runtime_outputs(MANIFEST, "early_3d")
    assert dropped == ()
    assert [o.channel for o in outputs] == [
        "soft_body", "weather", "lifecycle", "character_collision"]
    assert outputs[0].node_path == "/root/FrontierWorld/SoftBody/cape"
    assert outputs[2].payload["integrity"] == .9


def test_tile_era_drops_unsupported_channels_explicitly():
    outputs, dropped = route_runtime_outputs(MANIFEST, "tile_8bit")
    assert {o.channel for o in outputs} == {"weather", "lifecycle"}
    assert dropped == ("soft_body", "character_collision")


def test_budget_and_range_enforced():
    many = dict(MANIFEST, character_physics=None, soft_material_motion=[])
    many["structures"] = MANIFEST["structures"] * 65
    with pytest.raises(RuntimeBindingError, match="budget"):
        route_runtime_outputs(many, "tile_8bit")
    bad = dict(MANIFEST, structures=[dict(MANIFEST["structures"][0], integrity=1.5)])
    with pytest.raises(RuntimeBindingError, match="integrity"):
        route_runtime_outputs(bad, "early_3d")
    nan = dict(MANIFEST, weather_physics=dict(MANIFEST["weather_physics"],
                                              rain_mm_h=float("nan")))
    with pytest.raises(RuntimeBindingError, match="finite"):
        route_runtime_outputs(nan, "early_3d")


def test_custom_emitter_and_empty_emitter(candidate):
    binding = bind_scene_candidate(candidate, _auth(candidate), key=KEY, now_ms=2000,
                                   emitter=lambda c: {"a.gd": "extends Node"})
    assert set(binding.godot_files) == {"a.gd", "frontier/data/runtime_binding.json"}
    with pytest.raises(RuntimeBindingError, match="no source"):
        bind_scene_candidate(candidate, _auth(candidate), key=KEY, now_ms=2000,
                             emitter=lambda c: {})


def test_digest_of_is_canonical():
    assert digest_of({"b": 1, "a": 2}) == digest_of({"a": 2, "b": 1})
