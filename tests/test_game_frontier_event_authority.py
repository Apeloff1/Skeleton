"""GF-P0-98 / GF-P0-196: signed event authority over quest canon and save state."""
from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.forge.game_frontier_event_authority import (
    CanonRules, ControllerBinding, EventAuthorityError, QuestSpec, SaveState,
    approve_decision, commit_approved_events, verify_journal,
)
from skeleton.forge.game_frontier_rpg_events import (
    EnvironmentalTrigger, RPGEventAction, RPGEventPage, evaluate_environment_events,
)

KEY = b"era-authority-key-0001"
KEYS = {"warden": KEY}
CANON = CanonRules.build((
    QuestSpec("storm", ("begin", "shelter", "done")),
    QuestSpec("after", ("go",), prerequisites=("storm",)),
    QuestSpec("modern_only", ("x",), era_engines=frozenset({"modern_3d"})),
), immutable_flags=frozenset({"king_dead"}))
CONTROLLERS = {
    "guard": ControllerBinding("guard", "npc", frozenset({"early_3d"}), max_health=50),
    "lantern": ControllerBinding("lantern", "gear", frozenset({"early_3d"})),
}


def _decide(*actions, page="p", rain=10.0):
    page_obj = RPGEventPage(page, 0, (EnvironmentalTrigger("rain_mm_h", "above", 5.0),),
                            tuple(RPGEventAction(*a) for a in actions))
    result = evaluate_environment_events((page_obj,), current={"rain_mm_h": rain}, now_ms=10)
    assert result.accepted
    return result.accepted[0]


def _commit(state, *decisions, now=100, approvals=None):
    approvals = approvals or {
        d.evidence_digest: approve_decision(d, era_engine=state.era_engine,
                                            authority_id="warden", key=KEY)
        for d in decisions}
    return commit_approved_events(state, decisions, approvals, canon=CANON,
                                  controllers=CONTROLLERS, keys=KEYS, now_ms=now)


def test_quest_lifecycle_through_canon():
    s = SaveState("early_3d")
    s = _commit(s, _decide(("start_quest", "quest", "storm", ""))).state
    assert s.quest_stage["storm"] == 0
    s = _commit(s, _decide(("advance_quest", "quest", "storm", "shelter"), page="a")).state
    s = _commit(s, _decide(("advance_quest", "quest", "storm", ""), page="b")).state
    assert "storm" in s.completed_quests and "storm" not in s.quest_stage
    s = _commit(s, _decide(("start_quest", "quest", "after", ""), page="c")).state
    assert s.quest_stage["after"] == 0
    assert s.revision == 4


def test_prerequisite_and_stage_skip_rejected():
    s = SaveState("early_3d")
    with pytest.raises(EventAuthorityError, match="prerequisites"):
        _commit(s, _decide(("start_quest", "quest", "after", "")))
    s = _commit(s, _decide(("start_quest", "quest", "storm", ""))).state
    with pytest.raises(EventAuthorityError, match="one at a time"):
        _commit(s, _decide(("advance_quest", "quest", "storm", "done"), page="z"))


def test_era_scoped_quest_rejected():
    with pytest.raises(EventAuthorityError, match="not in era"):
        _commit(SaveState("early_3d"), _decide(("start_quest", "quest", "modern_only", "")))


def test_immutable_canon_flag():
    with pytest.raises(EventAuthorityError, match="immutable"):
        _commit(SaveState("early_3d"), _decide(("set_flag", "world", "king_dead", "false")))


def test_unsigned_or_forged_approval_rejected():
    d = _decide(("set_flag", "world", "wet", "true"))
    s = SaveState("early_3d")
    with pytest.raises(EventAuthorityError, match="not approved"):
        _commit(s, d, approvals={"x": None})
    forged = approve_decision(d, era_engine="early_3d", authority_id="warden",
                              key=b"attacker-key-000000")
    with pytest.raises(EventAuthorityError, match="signature"):
        _commit(s, d, approvals={d.evidence_digest: forged})
    other_era = approve_decision(d, era_engine="tile_8bit", authority_id="warden", key=KEY)
    with pytest.raises(EventAuthorityError, match="era"):
        _commit(s, d, approvals={d.evidence_digest: other_era})


def test_controller_actions_bounded_and_typed():
    s = SaveState("early_3d")
    s = _commit(s, _decide(("take_damage", "character", "guard", "30"))).state
    assert s.controller_health["guard"] == 20
    s = _commit(s, _decide(("take_damage", "character", "guard", "30"), page="q")).state
    assert s.controller_health["guard"] == 0
    s = _commit(s, _decide(("heal_health", "character", "guard", "50"), page="r")).state
    assert s.controller_health["guard"] == 50
    with pytest.raises(EventAuthorityError, match="cannot receive"):
        _commit(s, _decide(("heal_health", "character", "lantern", "1"), page="t"))
    with pytest.raises(EventAuthorityError, match="registered controller"):
        _commit(s, _decide(("take_damage", "character", "ghost", "1"), page="u"))


def test_controller_not_bound_in_era():
    with pytest.raises(EventAuthorityError, match="not bound"):
        _commit(SaveState("tile_8bit"), _decide(("take_damage", "character", "guard", "1")))


def test_batch_is_atomic():
    s = SaveState("early_3d")
    good = _decide(("award_xp", "character", "player", "10"), page="g")
    bad = _decide(("consume_item", "character", "potion", "1"), page="h")
    with pytest.raises(EventAuthorityError, match="more items"):
        _commit(s, good, bad)
    assert s.xp == 0 and s.revision == 0


def test_presentation_actions_deferred_not_saved():
    s = SaveState("early_3d")
    r = _commit(s, _decide(("play_music", "audio", "theme", "storm"),
                           ("award_xp", "character", "player", "5")))
    assert [a.kind for a in r.deferred_presentation] == ["play_music"]
    assert r.state.xp == 5
    assert r.state.last_fired_ms["p"] == 100


def test_journal_chain_verifies_and_detects_tamper():
    s = SaveState("early_3d")
    r = _commit(s, _decide(("award_xp", "character", "player", "5"),
                           ("set_flag", "world", "wet", "true")))
    assert verify_journal(r.journal) == r.state.journal_head
    tampered = (replace(r.journal[0], authority_id="mallory"),) + r.journal[1:]
    with pytest.raises(EventAuthorityError, match="tampered"):
        verify_journal(tampered)


def test_clock_cannot_move_backwards():
    s = _commit(SaveState("early_3d"), _decide(("award_xp", "character", "p", "1")),
                now=500).state
    with pytest.raises(EventAuthorityError, match="backwards"):
        _commit(s, _decide(("award_xp", "character", "p", "1"), page="x"), now=10)


def test_state_digest_changes_with_commit():
    s = SaveState("early_3d")
    after = _commit(s, _decide(("award_xp", "character", "p", "1"))).state
    assert s.digest != after.digest
