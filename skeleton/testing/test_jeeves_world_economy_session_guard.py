"""Atomic economy session choices: unaffordable moves never persist."""
from __future__ import annotations

import os
import pytest

from skeleton.jeeves.worlds.economy import EconomyStore, propose_economy
from skeleton.jeeves.worlds.economy_session import EconomySessionStore
from skeleton.jeeves.worlds.session import SessionStore
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, propose, prove,
)


def fixture(tmp_path):
    world = propose(world_id="harbor", premise="Original ration loop.",
                    protagonist="Ari", region="Harbor", goal="Finish the trip.")
    world["choices"].append({
        "id": "spend", "from": "opening", "to": "opening",
        "label": "Use a ration", "requires": [], "grants": [],
    })
    prove(world)
    WorldStore(tmp_path).publish(world, create=True)
    source = propose_economy(
        world, prompt="Spend a finite ration before reaching shore.",
        resource_id="rations", name="Rations", initial=1, capacity=2,
        choice_id="spend", cost=1, gain=0)
    economy = EconomyStore(tmp_path)
    lease = economy.publish("harbor", source, create=True)
    approved = economy.approve("harbor", lease, "Reviewed original economy.")
    sessions = SessionStore(tmp_path)
    sessions.create("harbor", "saveone")
    return economy, sessions, approved


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_atomic_choice_and_unaffordable_retry(tmp_path):
    economy, sessions, approved = fixture(tmp_path)
    player = economy.player("harbor", "saveone")
    assert [item["id"] for item in player["available_choices"]] == [
        "pursue_goal", "spend"]
    guard = EconomySessionStore(tmp_path)
    after = guard.choose(
        "harbor", "saveone", "spend",
        expected_session_digest=player["session_digest"],
        expected_economy_digest=approved)
    assert after["replay"]["balances"] == {"rations": 0}
    assert [item["id"] for item in after["available_choices"]] == ["pursue_goal"]
    with pytest.raises(CanonError, match="economy_unaffordable_transition"):
        guard.choose(
            "harbor", "saveone", "spend",
            expected_session_digest=after["session_digest"],
            expected_economy_digest=approved)
    assert sessions.read("harbor", "saveone")["choices"] == ["spend"]
    ended = guard.choose(
        "harbor", "saveone", "pursue_goal",
        expected_session_digest=after["session_digest"],
        expected_economy_digest=approved)
    assert ended["replay"]["ending"] is True
    assert ended["available_choices"] == []


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_stale_leases_and_forged_choice_rejected(tmp_path):
    economy, sessions, approved = fixture(tmp_path)
    player = economy.player("harbor", "saveone")
    guard = EconomySessionStore(tmp_path)
    for expected_session, expected_economy, choice, code in [
        ("0" * 64, approved, "spend", "economy_stale_session"),
        (player["session_digest"], "0" * 64, "spend", "economy_stale_source"),
        (player["session_digest"], approved, "unknown", "session_invalid_transition"),
    ]:
        with pytest.raises(CanonError, match=code):
            guard.choose(
                "harbor", "saveone", choice,
                expected_session_digest=expected_session,
                expected_economy_digest=expected_economy)
    assert sessions.read("harbor", "saveone")["choices"] == []
