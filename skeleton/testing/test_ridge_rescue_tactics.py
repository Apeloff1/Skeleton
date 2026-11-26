"""Real one-turn simulation, CAS publication and bounded tactics contracts."""
import json
from pathlib import Path

import pytest

from skeleton.game.gameplay.ridge_rescue.schema import parse_world
from skeleton.game.gameplay.ridge_rescue.journal import open_journal, verify_journal
from skeleton.game.gameplay.ridge_rescue.tactics import (
    TacticsError, parse_policy, suggest, advance, autoplay,
)
from skeleton.game.gameplay.ridge_rescue.tactics_editor import revise_policy, verify_policy_revision
from skeleton.game.gameplay.ridge_rescue.custody import digest, verify_run

HERE = Path(__file__).resolve().parents[1] / "game/gameplay/ridge_rescue"


def world():
    return parse_world((HERE / "cinder_ridge_acceptance.json").read_bytes())


def policy():
    return json.loads((HERE / "cinder_ridge_tactics.json").read_text(encoding="utf-8"))


def test_initial_tactics_are_legal_and_replayable():
    w = world()
    journal = open_journal(w)
    advice = suggest(w, journal, policy())
    assert advice["ranked"]
    assert advice["guaranteed"] is False
    assert advice["ranked"][0]["action"] == {"verb": "rescue", "target": "tavi"}
    committed = advance(w, journal, policy(), expected_head=journal["head"])
    assert committed["action"] == advice["ranked"][0]["action"]
    assert committed["journal"]["state"]["civilians"]["tavi"] == "rescued"
    assert verify_journal(committed["journal"])["head"] == committed["journal"]["head"]
    assert journal["entries"] == []


def test_stale_head_and_mismatched_world_refused():
    w = world()
    journal = open_journal(w)
    with pytest.raises(TacticsError, match="stale"):
        advance(w, journal, policy(), expected_head="0" * 64)
    from skeleton.game.gameplay.ridge_rescue.schema import world_dict
    changed = world_dict(w)
    changed["name"] = "Different world"
    with pytest.raises(TacticsError, match="differs"):
        suggest(parse_world(changed), journal, policy())


def test_autoplay_truthful_bounded_and_portable():
    w = world()
    p = {**policy(), "max_steps": 6}
    result = autoplay(w, p)
    assert 1 <= result["steps_executed"] <= 6
    assert result["guaranteed"] is False
    assert result["journal"]["state"]["turn"] == result["steps_executed"]
    assert verify_run(result["bundle"])["state"] == result["journal"]["state"]
    assert result["status"] == result["journal"]["state"]["status"]


@pytest.mark.parametrize("bad", [
    {"risk": True}, {"risk": -1}, {"max_steps": 0}, {"max_steps": 9999},
    {"objective": "admin"}, {"prefer_crafting": 1}, {"title": ""},
])
def test_bad_policy_rejected(bad):
    value = {**policy(), **bad}
    with pytest.raises(TacticsError):
        parse_policy(value)


def test_policy_edit_is_optimistic_and_preview_replayed():
    w = world()
    source = policy()
    op = {"expected_sha256": digest(parse_policy(source)), "field": "risk", "value": 20}
    revision = revise_policy(w, source, op)
    assert verify_policy_revision(w, source, op, revision)
    assert revision["policy"]["risk"] == 20
    with pytest.raises(TacticsError, match="stale"):
        revise_policy(w, source, {**op, "expected_sha256": "0" * 64})
    with pytest.raises(TacticsError):
        revise_policy(w, source, {**op, "field": "schema", "value": "evil"})


def test_advice_deterministic_and_rejects_tampered_journal():
    w = world()
    journal = open_journal(w)
    assert suggest(w, journal, policy()) == suggest(w, journal, policy())
    journal["state"]["inventory"]["signal"] = 99
    with pytest.raises(TacticsError):
        suggest(w, journal, policy())
