"""Deterministic end-user campaign acceptance and hostile portable-save fixtures."""
import copy
import json

import pytest

from skeleton.game.gameplay.quest_chapter_campaign import (
    SCHEMA, _step, cli, demo_campaign_actions, export_campaign,
    import_campaign, new_campaign, normalize_campaign, original_campaign,
    resume_campaign, simulate_campaign, verify_campaign,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def _finished():
    return simulate_campaign(original_campaign(), demo_campaign_actions())


def test_original_campaign_is_end_to_end_playable_and_replayable():
    session = _finished()
    assert session["schema_version"] == SCHEMA
    assert session["state"]["phase"] == "won"
    assert session["state"]["chapter_index"] == 2
    assert session["state"]["flags"] == ["beacon_raised", "harbor_secured"]
    assert [event["ending"] for event in session["state"]["history"]] == [
        "beacon_lit", "beacon_lit",
    ]
    assert verify_campaign(json.loads(json.dumps(session))) == session
    assert import_campaign(json.loads(json.dumps(export_campaign(session)))) == session


def test_checkpoint_resume_matches_one_pass_byte_for_byte():
    source = original_campaign()
    actions = demo_campaign_actions()
    first = simulate_campaign(source, actions[:7])
    checkpoint = json.loads(json.dumps(first))
    second = resume_campaign(checkpoint, actions[7:17])
    resumed = resume_campaign(second, actions[17:])
    assert resumed == simulate_campaign(source, actions)


def test_campaign_requires_earned_chapter_completion_before_advancing():
    source = original_campaign()
    session = new_campaign(source)
    with pytest.raises(CombatSessionError, match="not reached"):
        _step(session, {"kind": "advance"})
    with pytest.raises(CombatSessionError, match="unsupported"):
        _step(session, {"kind": "grant", "flag": "harbor_secured"})
    with pytest.raises(CombatSessionError, match="invalid campaign action"):
        _step(session, {"kind": True})
    with pytest.raises(CombatSessionError, match="chapter quest action"):
        _step(session, {"kind": "quest", "action": []})


def test_alternate_ending_blocks_future_chapters_without_granting_flags():
    source = original_campaign()
    actions = demo_campaign_actions()
    actions[10] = {"kind": "quest", "action": {
        "kind": "finish", "ending_id": "quiet_victory",
    }}
    blocked = simulate_campaign(source, actions[:12])
    assert blocked["state"]["phase"] == "blocked"
    assert blocked["state"]["flags"] == []
    assert blocked["state"]["history"][0]["accepted"] is False
    assert verify_campaign(blocked) == blocked
    with pytest.raises(CombatSessionError, match="terminal"):
        _step(blocked, actions[12])


@pytest.mark.parametrize("mutation", [
    lambda s: s.update(source_digest="0" * 64),
    lambda s: s["state"].update(flags=["harbor_secured"]),
    lambda s: s["state"]["history"][0].update(accepted=False),
    lambda s: s["state"].update(chapter_index=1),
    lambda s: s["state"].update(phase="lost"),
    lambda s: s["journal"][0].update(receipt="0" * 64),
    lambda s: s["journal"][1]["action"].update(kind="advance"),
    lambda s: s["save"].update(parent_save_digest=None),
])
def test_tampered_campaign_save_is_rejected(mutation):
    saved = simulate_campaign(original_campaign(), demo_campaign_actions()[:4])
    if not saved["state"]["history"]:
        saved = _finished()
    bad = copy.deepcopy(saved)
    mutation(bad)
    assert bad != saved, "tamper fixture must modify the checkpoint"
    with pytest.raises(CombatSessionError):
        verify_campaign(bad)


@pytest.mark.parametrize("mutation", [
    lambda s: s.update(schema_version="v2"),
    lambda s: s["chapters"].append(copy.deepcopy(s["chapters"][0])),
    lambda s: s["chapters"][1].update(id="beacon"),
    lambda s: s["chapters"][1]["quest"].update(quest_id="lantern_beacon"),
    lambda s: s["chapters"][1].update(required_ending="nonexistent"),
    lambda s: s["chapters"][0].update(requires_flags=["harbor_secured"]),
    lambda s: s["chapters"][1].update(grants_flags=["beacon_raised"]),
    lambda s: s["chapters"][1]["quest"].update(world_id="other_world"),
    lambda s: s["chapters"][0].update(grants_flags=["beacon_raised", "beacon_raised"]),
])
def test_invalid_source_or_progression_is_rejected(mutation):
    source = original_campaign()
    mutation(source)
    with pytest.raises(CombatSessionError):
        normalize_campaign(source)


def test_bundle_rejects_corruption_and_wrong_source():
    session = _finished()
    bundle = export_campaign(session)
    bad = copy.deepcopy(bundle)
    bad["checksum"] = "0" * 64
    with pytest.raises(CombatSessionError, match="checksum"):
        import_campaign(bad)
    bad = copy.deepcopy(bundle)
    bad["source_digest"] = "0" * 64
    bad["checksum"] = __import__(
        "skeleton.game.gameplay.flgb_gameplay_runtime", fromlist=["dig"]
    ).dig({k: v for k, v in bad.items() if k != "checksum"})
    with pytest.raises(CombatSessionError, match="identity"):
        import_campaign(bad)
    bad = copy.deepcopy(bundle)
    bad["state_digest"] = "0" * 64
    bad["checksum"] = __import__(
        "skeleton.game.gameplay.flgb_gameplay_runtime", fromlist=["dig"]
    ).dig({k: v for k, v in bad.items() if k != "checksum"})
    with pytest.raises(CombatSessionError, match="identity"):
        import_campaign(bad)


def test_bounded_actions_and_terminal_replay():
    source = original_campaign()
    with pytest.raises(CombatSessionError, match="action batch"):
        simulate_campaign(source, [{"kind": "advance"}] * 97)
    done = _finished()
    with pytest.raises(CombatSessionError, match="terminal"):
        resume_campaign(done, [{"kind": "advance"}])


def test_cli_is_reachable_and_errors_are_nonzero(capsys):
    from skeleton.__main__ import main
    assert main(["quest-campaign", "demo"]) == 0
    session = json.loads(capsys.readouterr().out)
    assert session["state"]["phase"] == "won"
    assert cli(["verify", "--session-json", json.dumps(session)]) == 0
    assert json.loads(capsys.readouterr().out) == session
    assert cli(["simulate", "--source-json", '{"bad":true}',
                "--actions-json", "[]"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False


def test_forged_active_quest_digest_is_rejected():
    saved = simulate_campaign(original_campaign(), demo_campaign_actions()[:4])
    saved["state"]["active_quest"]["state_digest"] = "0" * 64
    with pytest.raises(CombatSessionError):
        verify_campaign(saved)
