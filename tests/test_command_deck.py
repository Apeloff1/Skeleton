"""Tests for the command deck integration layer.

Covers policy, verification, repair, lattice, steering, KV cache,
mouth binding, LoRA, and decoder subsystem wiring.
"""
from __future__ import annotations

import pytest

from skeleton.cortex.deck import CommandDeck


class TestCommandDeckPolicy:
    def test_policy_state(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        state = deck.policy_state()
        assert "thresholds" in state
        assert "repair_surfaces_active" in state

    def test_policy_gate_pass(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        result = deck.policy_gate("forge", 0.9)
        assert result["passed"] is True
        assert result["margin"] > 0

    def test_policy_gate_fail(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        result = deck.policy_gate("forge", 0.3)
        assert result["passed"] is False

    def test_save_and_rollback_version(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        vid = deck.save_policy_version(comment="test version", author="pytest")
        assert vid.startswith("pv-")
        versions = deck.policy_versions(limit=8)
        assert versions["total_versions"] >= 1

    def test_policy_diff(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        v1 = deck.save_policy_version(comment="v1")
        v2 = deck.save_policy_version(comment="v2")
        diff = deck.policy_diff(v1, v2)
        assert diff["kind"] == "policy-diff"

    def test_rollback_preview(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        vid = deck.save_policy_version(comment="preview test")
        preview = deck.rollback_preview(vid)
        assert preview["kind"] == "rollback-preview"
        assert preview["ok"] == 1

    def test_policy_lineage(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        vid = deck.save_policy_version(comment="lineage test")
        lineage = deck.policy_lineage(vid)
        assert isinstance(lineage, list)
        assert len(lineage) >= 1


class TestCommandDeckRepair:
    def test_repair_sessions_empty(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        sessions = deck.repair_sessions("forge")
        assert sessions["kind"] == "repair-session-card"
        assert sessions["total_sessions"] == 0

    def test_repair_effectiveness_empty(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        eff = deck.repair_effectiveness("forge")
        assert eff["n"] == 0

    def test_repair_telemetry_empty(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        telem = deck.repair_telemetry("forge")
        assert telem["kind"] == "repair-telemetry-card"
        assert telem["n"] == 0

    def test_repair_errors_empty(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        errs = deck.repair_errors("forge")
        assert errs["kind"] == "repair-error-summary"
        assert errs["total_errors"] == 0

    def test_repair_learned_empty(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        learned = deck.repair_learned()
        assert learned["kind"] == "learned-policy-card"

    def test_repair_strategy_unknown(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        strat = deck.repair_strategy("forge", "unknown_reason")
        assert strat["kind"] == "repair-strategy-suggestion"
        assert strat["known"] is False


class TestCommandDeckVerification:
    def test_verify_forge_empty(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        result = deck.verify_forge({})
        assert "accepted" in result

    def test_verify_plan_empty(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        result = deck.verify_plan({})
        assert "accepted" in result

    def test_verify_pipeline_empty(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        result = deck.verify_pipeline({})
        assert "accepted" in result

    def test_verify_npc_empty(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        result = deck.verify_npc({})
        assert "accepted" in result

    def test_verify_dialogue_empty(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        result = deck.verify_dialogue({})
        assert "accepted" in result


class TestCommandDeckAdvanced:
    def test_lattice_hud(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        card = deck.lattice_hud()
        assert card["kind"] == "pixel-lattice-card"
        assert "viewport" in card["regions"]

    def test_lattice_editor(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        card = deck.lattice_editor()
        assert card["kind"] == "pixel-lattice-card"
        assert "canvas" in card["regions"]

    def test_steering_register(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        vec = deck.steering_register("test_vec", strength=1.5)
        assert vec["name"] == "test_vec"
        assert vec["strength"] == 1.5

    def test_steering_activate_deactivate(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        deck.steering_register("active_vec")
        deck.steering_activate("active_vec", weight=0.8)
        comp = deck.steering_composite()
        assert "active_vec" in comp["card"]["active_vectors"]
        deck.steering_deactivate("active_vec")
        comp2 = deck.steering_composite()
        assert "active_vec" not in comp2["card"]["active_vectors"]

    def test_kv_cache_stats(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        stats = deck.kv_cache_stats()
        assert stats["kind"] == "octahedral-kv-cache-card"
        assert stats["entries"] == 0

    def test_mouth_feed_and_current(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        target = deck.mouth_feed("AA", 1000.0, confidence=1.0)
        assert "viseme" in target
        current = deck.mouth_current()
        assert current["viseme"] == target["viseme"]

    def test_lora_card(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        card = deck.lora_card()
        assert card["kind"] == "parametric-lora-card"
        assert card["layers"] == 0

    def test_decoder_card(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        card = deck.decoder_card()
        assert card["kind"] == "gpu-decoder-prior-card"
        assert card["decode_count"] == 0

    def test_master_card(self, tmp_path):
        deck = CommandDeck(root=tmp_path)
        master = deck.master_card()
        assert master["kind"] == "command-deck-master"
        assert "policy" in master
        assert "steering" in master
        assert "kv_cache" in master
        assert "mouth" in master
        assert "lora" in master
        assert "decoder" in master
        assert "lattice_hud" in master
        assert "lattice_editor" in master
