"""Policy command surface tests."""
from __future__ import annotations

from skeleton.cortex.deck import CommandDeck
from skeleton.testing.test_cortex_deck import _Dummy


def test_deck_policy_cards(tmp_path):
    deck = CommandDeck(_Dummy(), root=tmp_path)
    assert deck.policy()["kind"] == "policy-control-card"
    assert deck.threshold(surface="forge")["kind"] == "threshold-card"


def test_deck_policy_updates(tmp_path):
    deck = CommandDeck(_Dummy(), root=tmp_path)
    out = deck.set_threshold("forge", 0.81)
    assert out["threshold"] == 0.81
    out = deck.set_repair_enabled("npc", False)
    assert out["enabled"] is False
    out = deck.set_repair_class("scene_stub", False)
    assert out["enabled"] is False
