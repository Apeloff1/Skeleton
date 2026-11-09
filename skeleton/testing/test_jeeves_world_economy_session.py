"""Saved world sessions replay through the reviewed economy, never trusting balances."""
from __future__ import annotations

import os
import pytest

from skeleton.jeeves.worlds.economy import (
    EconomyStore, propose_economy, replay_economy,
)
from skeleton.jeeves.worlds.session import SessionStore
from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, propose,
)


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_source_verified_saved_player_session(tmp_path):
    world = propose(world_id="harbor", premise="Original voyage.",
                    protagonist="Ari", region="Harbor", goal="Reach shore.")
    WorldStore(tmp_path).publish(world, create=True)
    store = EconomyStore(tmp_path)
    source = propose_economy(
        world, prompt="Use one ration.", resource_id="rations",
        name="Rations", initial=1, capacity=4, choice_id="pursue_goal",
        cost=1, gain=0)
    lease = store.publish("harbor", source, create=True)
    approved = store.approve("harbor", lease, "Reviewed original ration rules.")
    sessions = SessionStore(tmp_path)
    created = sessions.create("harbor", "saveone")
    start = store.player("harbor", "saveone")
    assert start["replay"]["balances"] == {"rations": 1}
    sessions.choose("harbor", "saveone", "pursue_goal",
                    created["session_digest"])
    player = store.player("harbor", "saveone")
    assert player["replay"]["ending"] is True
    assert player["replay"]["balances"] == {"rations": 0}
    assert player["session_digest"] != start["session_digest"]
    store.compile("harbor", approved)
    assert store.verify("harbor")["economy_digest"] == approved
    with pytest.raises(CanonError, match="economy_invalid_transition"):
        replay_economy(source, world, ["pursue_goal", "pursue_goal"])


@pytest.mark.skipif(os.name != "posix", reason="descriptor-anchored custody")
def test_unreviewed_source_cannot_read_player(tmp_path):
    world = propose(world_id="harbor", premise="Original voyage.",
                    protagonist="Ari", region="Harbor", goal="Reach shore.")
    WorldStore(tmp_path).publish(world, create=True)
    SessionStore(tmp_path).create("harbor", "saveone")
    store = EconomyStore(tmp_path)
    source = propose_economy(
        world, prompt="Use one ration.", resource_id="rations",
        name="Rations", initial=1, capacity=4, choice_id="pursue_goal",
        cost=1, gain=0)
    store.publish("harbor", source, create=True)
    with pytest.raises(CanonError, match="economy_review_required"):
        store.player("harbor", "saveone")
