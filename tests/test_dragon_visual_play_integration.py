"""Real original-game visual play and consent/error boundary regression."""
from dataclasses import replace
import pytest

from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.webcrawler.dragon_reference_game_adapter import ReferenceGameVisualAdapter, reference_visual_policy
from skeleton.ai.webcrawler.dragon_visual_play import DragonVisualPlayer, PlayAction, PlayGrant, VisualFrame, frame_change


def setup(seed=41):
    world = generate_playable_world(GameBuildIntent("dragon-play", "Canal Quest", "Original visual practice",
        seed, width=9, height=9, levels=2, collectibles_per_level=1, hazards_per_level=0), authorized=True)
    adapter = ReferenceGameVisualAdapter(world, authorized=True)
    grant = PlayGrant("owner", "session", adapter.adapter_id, world.digest,
        frozenset({"up", "down", "left", "right"}), 100, max_steps=600)
    return adapter, grant


@pytest.mark.parametrize("seed", [1, 12, 41, 99, 2026])
def test_dragon_visually_completes_real_original_game(seed):
    adapter, grant = setup(seed)
    player = DragonVisualPlayer(adapter, grant, consent_current=lambda g: True, clock=lambda: 1)
    trace = player.run(reference_visual_policy)
    assert trace.stop_reason == "terminal_observed" and adapter.state.status == "won"
    assert adapter.inputs_released and trace.steps[-1]["action"] is None
    assert trace.to_payload()["release_authority"] is False
    for before, after in zip(trace.steps, trace.steps[1:]):
        assert after["previous_digest"] == before["step_digest"]
    with pytest.raises(PermissionError, match="consumed"):
        player.run(reference_visual_policy)


def test_revocation_stops_before_game_control_and_releases_inputs():
    adapter, grant = setup()
    trace = DragonVisualPlayer(adapter, grant, consent_current=lambda g: False, clock=lambda: 1).run(reference_visual_policy)
    assert trace.stop_reason == "revoked" and not trace.steps and adapter.state.steps == 0
    assert adapter.inputs_released


def test_revocation_during_policy_prevents_input():
    adapter, grant = setup()
    consent = [True]
    def policy(frame):
        consent[0] = False
        return reference_visual_policy(frame)
    trace = DragonVisualPlayer(adapter, grant, consent_current=lambda g: consent[0], clock=lambda: 1).run(policy)
    assert trace.stop_reason == "revoked" and adapter.state.steps == 0


def test_disallowed_control_and_policy_crash_release_inputs():
    for callback in (lambda f: PlayAction(frozenset({"system-menu"})), lambda f: 1/0):
        adapter, grant = setup()
        with pytest.raises((PermissionError, ZeroDivisionError)):
            DragonVisualPlayer(adapter, grant, consent_current=lambda g: True, clock=lambda: 1).run(callback)
        assert adapter.inputs_released and adapter.state.steps == 0


def test_frame_replay_is_rejected_and_inputs_released():
    adapter, grant = setup()
    original = adapter.capture
    adapter.capture = lambda: replace(original(), sequence=0)
    with pytest.raises(ValueError, match="sequence replay"):
        DragonVisualPlayer(adapter, grant, consent_current=lambda g: True, clock=lambda: 1).run(reference_visual_policy)
    assert adapter.inputs_released


def test_target_rebinding_expiry_and_step_budget_fail_closed():
    adapter, grant = setup()
    trace = DragonVisualPlayer(adapter, replace(grant, expires_at=1), consent_current=lambda g: True, clock=lambda: 1).run(reference_visual_policy)
    assert trace.stop_reason == "expired" and not trace.steps
    adapter, grant = setup()
    player = DragonVisualPlayer(adapter, grant, consent_current=lambda g: True, clock=lambda: 1)
    adapter.artifact_digest = "f"*64
    assert player.run(reference_visual_policy).stop_reason == "target_changed"
    adapter, grant = setup()
    trace = DragonVisualPlayer(adapter, replace(grant, max_steps=1), consent_current=lambda g: True, clock=lambda: 1).run(reference_visual_policy)
    assert trace.stop_reason == "step_budget" and len(trace.steps) == 1


def test_rgb_change_is_observation_not_a_mechanic_claim():
    first = VisualFrame(0, 1, 1, bytes((0, 0, 0)))
    second = VisualFrame(1, 1, 1, bytes((1, 0, 0)))
    assert frame_change(first, second)["fraction"] == 1
    assert frame_change(first, second)["mechanic_classification"] == "unclassified"
    with pytest.raises(ValueError):
        VisualFrame(0, 1, 1, b"wrong")
