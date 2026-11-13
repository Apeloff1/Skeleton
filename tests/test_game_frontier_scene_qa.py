"""GF-P0-185: qualified physics/event evidence -> rendered-world scene QA."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

import pytest

from skeleton.game.simulation import CharacterController
from skeleton.game.simulation.multi_actor_semantic import ActorBody, run_actors
from skeleton.jeeves.game_frontier_runtime_binding import (
    authorise_candidate, bind_scene_candidate,
)
from skeleton.jeeves.game_frontier_scene_qa import (
    BINDING_FILE, RenderedWorldReport, SceneQAError, qualify_playable_scene,
)
from tests.test_game_frontier_godot import source_scene

KEY = b"operator-key-0123456789"


@pytest.fixture(scope="module")
def binding():
    c = source_scene(fps=60)
    auth = authorise_candidate(c.manifest_digest, operator_id="ops", era="early_3d",
                               issued_ms=0, ttl_ms=10_000, key=KEY)
    return bind_scene_candidate(c, auth, key=KEY, now_ms=1)


@pytest.fixture(scope="module")
def physics():
    a = ActorBody(CharacterController("a", (0, 500, 0), 5000, True), (300, 500, 300), 70_000)
    b = ActorBody(CharacterController("b", (500, 500, 0), 5000, True), (300, 500, 300), 70_000)
    return run_actors((a, b), [{}] * 10, step_ns=16_000_000)


def _report(binding, **kw):
    args = dict(godot_version="4.3.stable",
                loaded_binding_sha256=sha256(binding.godot_files[BINDING_FILE].encode()).hexdigest(),
                frames_rendered=180, frame_times_ms=(16.6,) * 180,
                nonblank_fraction=0.98,
                node_paths_seen=frozenset(o.node_path for o in binding.outputs),
                script_errors=0)
    args.update(kw)
    return RenderedWorldReport(**args)


def test_pending_without_native_render(binding, physics):
    v = qualify_playable_scene(binding, physics, None)
    assert v.verdict == "pending_native_render" and not v.playable
    assert v.physics_ticks == 10 and v.physics_events["contact_begin"] == 1


def test_playable_with_matching_render(binding, physics):
    v = qualify_playable_scene(binding, physics, _report(binding))
    assert v.playable and v.failures == ()
    assert v.p95_frame_ms == pytest.approx(16.6)


def test_render_failures_reported(binding, physics):
    v = qualify_playable_scene(binding, physics, _report(
        binding, loaded_binding_sha256="0" * 64, frames_rendered=10,
        frame_times_ms=(50.0,) * 10, nonblank_fraction=0.2, script_errors=3))
    assert not v.playable and v.verdict == "failed"
    assert set(v.failures) >= {"godot_loaded_different_binding", "too_few_frames",
                               "frame_pacing_over_budget", "blank_frames", "script_errors"}


def test_broken_physics_chain_rejected(binding, physics):
    broken = (physics[0], replace(physics[1], prev_digest="f" * 64)) + physics[2:]
    with pytest.raises(SceneQAError, match="chain"):
        qualify_playable_scene(binding, broken, None)
    with pytest.raises(SceneQAError, match="evidence"):
        qualify_playable_scene(binding, (), None)


def test_report_validation():
    with pytest.raises(SceneQAError, match="Godot 4"):
        RenderedWorldReport("3.5", "0" * 64, 0, (), 1.0, frozenset(), 0)
    with pytest.raises(SceneQAError, match="one frame time"):
        RenderedWorldReport("4.2", "0" * 64, 2, (1.0,), 1.0, frozenset(), 0)


def test_qa_digest_deterministic(binding, physics):
    a = qualify_playable_scene(binding, physics, _report(binding))
    b = qualify_playable_scene(binding, physics, _report(binding))
    assert a.qa_digest == b.qa_digest
