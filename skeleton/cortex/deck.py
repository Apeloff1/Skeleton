"""Command deck — operator control surface for all Skeleton subsystems.

Wires together policy, verification, repair, versioning, lattice,
steering, and advanced subsystems into a single operator-facing deck.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

# Core policy surfaces
from skeleton.organism.policy_enforcement import gate_check, policy_summary, repair_gate, threshold_for
from skeleton.organism.policy_versioning import (
    diff_versions,
    inherit_version,
    list_versions,
    rollback,
    rollback_by_surface,
    save_version,
    version_card,
    version_lineage,
)
from skeleton.organism.policy_rollback_control import rollback_control_card, rollback_preview

# Verification surfaces
from skeleton.intelligence.forge_verifier import ForgeVerifier
from skeleton.intelligence.plan_verifier import PlanVerifier
# PipelineVerifier imported lazily in verify_pipeline() to avoid import cycles
from skeleton.intelligence.npc_verifier import NPCVerifier
from skeleton.intelligence.dialogue_verifier import DialogueVerifier

# Repair surfaces
from skeleton.intelligence.repair_autonomy import repair_effectiveness, repair_session_card, run_multi_pass
from skeleton.intelligence.repair_orchestrator import orchestrated_repair, repair_orchestrator_card
from skeleton.intelligence.repair_telemetry import telemetry_card, error_summary
from skeleton.intelligence.learned_repair import learned_policy_card, suggest_repair_strategy

# Advanced subsystems
from skeleton.organism.pixel_lattice import default_editor_lattice, default_hud_lattice, lattice_card
from skeleton.organism.advanced_operator_steering import AdvancedOperatorSteering
from skeleton.intelligence.octahedral_kv_cache import OctahedralKVCache
from skeleton.intelligence.live_teacher_mouth import LiveMouthBinding
from skeleton.intelligence.parametric_lora import ParametricLoRAWriteBack
from skeleton.intelligence.gpu_decoder_prior import GPUDecoderPrior


class CommandDeck:
    """Central operator deck exposing all control surfaces."""

    def __init__(self, root=None):
        self.root = root
        self._steering = AdvancedOperatorSteering(dim=64)
        self._kv_cache = OctahedralKVCache(max_entries=4096)
        self._mouth = LiveMouthBinding(smoothing_window=3)
        self._lora = ParametricLoRAWriteBack(base_dim=768, default_rank=8)
        self._decoder = GPUDecoderPrior(patch_size=32, latent_dim=64)

    # ── Policy ──────────────────────────────────────────────

    def policy_state(self) -> Dict[str, Any]:
        return policy_summary(root=self.root)

    def policy_gate(self, surface: str, score: float) -> Dict[str, Any]:
        return gate_check(surface, score, root=self.root)

    def save_policy_version(self, comment: str = "", author: str = "operator") -> str:
        return save_version(comment=comment, author=author, root=self.root)

    def rollback_policy(self, version_id: str) -> Dict[str, Any]:
        return rollback(version_id, root=self.root)

    def rollback_policy_surface(self, surface: str) -> Dict[str, Any]:
        return rollback_by_surface(surface, root=self.root)

    def policy_versions(self, limit: int = 8) -> Dict[str, Any]:
        return version_card(root=self.root, limit=limit)

    def policy_diff(self, a: str, b: str) -> Dict[str, Any]:
        return diff_versions(a, b, root=self.root)

    def policy_lineage(self, version_id: str) -> List[str]:
        return version_lineage(version_id, root=self.root)

    def rollback_preview(self, version_id: str) -> Dict[str, Any]:
        return rollback_preview(version_id, root=self.root)

    # ── Verification ──────────────────────────────────────────

    def verify_forge(self, files, request: str = "") -> Dict[str, Any]:
        v = ForgeVerifier(root=self.root)
        return v.verify(files, request=request).to_dict()

    def verify_plan(self, plan) -> Dict[str, Any]:
        v = PlanVerifier(root=self.root)
        return v.verify(plan).to_dict()

    def verify_pipeline(self, tree) -> Dict[str, Any]:
        from skeleton.intelligence.pipeline_verifier import PipelineVerifier
        v = PipelineVerifier(root=self.root)
        return v.verify(tree).to_dict()

    def verify_npc(self, spec) -> Dict[str, Any]:
        v = NPCVerifier(root=self.root)
        return v.verify(spec).to_dict()

    def verify_dialogue(self, script) -> Dict[str, Any]:
        v = DialogueVerifier(root=self.root)
        return v.verify(script).to_dict()

    # ── Repair ──────────────────────────────────────────────

    def repair_orchestrate(self, surface: str, target_id: str, **kwargs) -> Dict[str, Any]:
        return orchestrated_repair(surface, target_id, root=self.root, **kwargs)

    def repair_sessions(self, surface: str = "") -> Dict[str, Any]:
        return repair_session_card(surface=surface, root=self.root)

    def repair_effectiveness(self, surface: str = "") -> Dict[str, Any]:
        return repair_effectiveness(surface=surface, root=self.root)

    def repair_telemetry(self, surface: str = "") -> Dict[str, Any]:
        return telemetry_card(surface=surface, root=self.root)

    def repair_errors(self, surface: str = "") -> Dict[str, Any]:
        return error_summary(surface=surface, root=self.root)

    def repair_learned(self) -> Dict[str, Any]:
        return learned_policy_card(root=self.root)

    def repair_strategy(self, surface: str, reason: str) -> Dict[str, Any]:
        return suggest_repair_strategy(surface, reason, root=self.root)

    # ── Advanced subsystems ───────────────────────────────────

    def lattice_hud(self) -> Dict[str, Any]:
        return lattice_card(default_hud_lattice())

    def lattice_editor(self) -> Dict[str, Any]:
        return lattice_card(default_editor_lattice())

    def steering_register(self, name: str, dims=None, strength: float = 1.0) -> Dict[str, Any]:
        vec = self._steering.register(name, dims=dims, strength=strength)
        return vec.to_dict()

    def steering_activate(self, name: str, weight: float = 1.0) -> None:
        self._steering.activate(name, weight)

    def steering_deactivate(self, name: str) -> None:
        self._steering.deactivate(name)

    def steering_composite(self) -> Dict[str, Any]:
        return {"composite": self._steering.composite_vector(), "card": self._steering.card()}

    def kv_cache_stats(self) -> Dict[str, Any]:
        return self._kv_cache.card()

    def mouth_feed(self, phoneme: str, ts_ms: float, confidence: float = 1.0) -> Dict[str, Any]:
        return self._mouth.feed_phoneme(phoneme, ts_ms, confidence).to_dict()

    def mouth_current(self) -> Dict[str, Any]:
        return self._mouth.current().to_dict()

    def lora_card(self) -> Dict[str, Any]:
        return self._lora.card()

    def decoder_card(self) -> Dict[str, Any]:
        return self._decoder.card()

    # ── Master card ─────────────────────────────────────────

    def master_card(self) -> Dict[str, Any]:
        return {
            "kind": "command-deck-master",
            "policy": self.policy_state(),
            "versions": self.policy_versions(limit=4),
            "rollback": rollback_control_card(root=self.root),
            "repair_orchestrator": repair_orchestrator_card(root=self.root),
            "steering": self._steering.card(),
            "kv_cache": self.kv_cache_stats(),
            "mouth": self._mouth.card(),
            "lora": self.lora_card(),
            "decoder": self.decoder_card(),
            "lattice_hud": self.lattice_hud(),
            "lattice_editor": self.lattice_editor(),
            "stored_prose": 0,
        }


_LIVE = None


def live_deck(root=None) -> CommandDeck:
    global _LIVE
    if _LIVE is None or (root is not None and getattr(_LIVE, "root", None) != root):
        _LIVE = CommandDeck(root=root)
    return _LIVE
