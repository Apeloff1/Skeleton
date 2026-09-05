"""Integration tests for the command deck wiring all subsystems."""
from __future__ import annotations

import pytest

from skeleton.cortex.deck import CommandDeck


class TestCommandDeckPolicy:
    def test_policy_state(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        state = deck.policy_state()
        assert "thresholds" in state
        assert "repair_surfaces_active" in state

    def test_policy_gate(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        result = deck.policy_gate("forge", 0.8)
        assert result["passed"] is True
        assert result["margin"] > 0

    def test_save_and_rollback_version(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        vid = deck.save_policy_version(comment="test")
        assert vid.startswith("pv-")
        versions = deck.policy_versions(limit=4)
        assert versions["total_versions"] >= 1


class TestCommandDeckVerification:
    def test_verify_forge_empty(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        result = deck.verify_forge({})
        assert "accepted" in result

    def test_verify_plan_empty(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        result = deck.verify_plan({})
        assert "accepted" in result


class TestCommandDeckRepair:
    def test_repair_sessions_empty(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        result = deck.repair_sessions("forge")
        assert result["kind"] == "repair-session-card"
        assert result["total_sessions"] == 0

    def test_repair_learned_empty(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        result = deck.repair_learned()
        assert result["kind"] == "learned-policy-card"

    def test_repair_strategy(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        result = deck.repair_strategy("forge", "low_score")
        assert result["kind"] == "repair-strategy-suggestion"


class TestCommandDeckAdvanced:
    def test_lattice_hud(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        result = deck.lattice_hud()
        assert result["kind"] == "pixel-lattice-card"
        assert "viewport" in result["regions"]

    def test_lattice_editor(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        result = deck.lattice_editor()
        assert result["kind"] == "pixel-lattice-card"
        assert "canvas" in result["regions"]

    def test_steering_register(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        result = deck.steering_register("test", dims=[1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        assert result["name"] == "test"

    def test_steering_activate_deactivate(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        deck.steering_register("a", dims=[1.0] + [0.0] * 63)
        deck.steering_activate("a", weight=0.5)
        result = deck.steering_composite()
        assert "composite" in result
        assert result["card"]["active_vectors"] == ["a"]

    def test_kv_cache_stats(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        result = deck.kv_cache_stats()
        assert result["kind"] == "octahedral-kv-cache-card"

    def test_mouth_feed(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        result = deck.mouth_feed("AA", 0.0)
        assert result["viseme"] == "ah"

    def test_mouth_current(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        deck.mouth_feed("AA", 0.0)
        result = deck.mouth_current()
        assert result["viseme"] == "ah"

    def test_lora_card(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        result = deck.lora_card()
        assert result["kind"] == "parametric-lora-card"

    def test_decoder_card(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        result = deck.decoder_card()
        assert result["kind"] == "gpu-decoder-prior-card"

    def test_master_card(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        result = deck.master_card()
        assert result["kind"] == "command-deck-master"
        assert "policy" in result
        assert "versions" in result
        assert "repair_orchestrator" in result
        assert "steering" in result
        assert "kv_cache" in result
        assert "mouth" in result
        assert "lora" in result
        assert "decoder" in result
        assert "lattice_hud" in result
        assert "lattice_editor" in result
