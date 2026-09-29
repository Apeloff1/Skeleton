"""Operator adapters for the canonical policy and generation components.

Each deck owns its in-memory controls; persisted policy and repair evidence
use its configured root. No success or health values are synthesized here.
"""
from __future__ import annotations

from skeleton.organism import policy_enforcement, policy_versioning
from skeleton.organism.policy_rollback_control import rollback_preview
from skeleton.organism.pixel_lattice import default_editor_lattice, default_hud_lattice, lattice_card
from skeleton.organism.advanced_operator_steering import AdvancedOperatorSteering
from skeleton.intelligence import learned_repair, repair_autonomy, repair_telemetry
from skeleton.intelligence.repair_orchestrator import orchestrated_repair
from skeleton.intelligence.live_teacher_mouth import LiveMouthBinding
from skeleton.intelligence.octahedral_kv_cache import OctahedralKVCache
from skeleton.intelligence.parametric_lora import ParametricLoRAWriteBack
from skeleton.intelligence.gpu_decoder_prior import GPUDecoderPrior
from skeleton.intelligence.forge_verifier import ForgeVerifier
from skeleton.intelligence.plan_verifier import PlanVerifier
from skeleton.intelligence.pipeline_verifier import PipelineVerifier
from skeleton.intelligence.npc_verifier import NpcVerifier
from skeleton.intelligence.dialogue_verifier import DialogueVerifier


class DeckOperations:
    def _init_operations(self):
        self.steering = AdvancedOperatorSteering()
        self.kv_cache = OctahedralKVCache()
        self.mouth = LiveMouthBinding()
        self.lora = ParametricLoRAWriteBack()
        self.decoder = GPUDecoderPrior()
        self.hud_lattice = default_hud_lattice()
        self.editor_lattice = default_editor_lattice()
        self.verifiers = {
            "forge": ForgeVerifier(root=self.root),
            "plan": PlanVerifier(root=self.root),
            "pipeline": PipelineVerifier(root=self.root),
            "npc": NpcVerifier(root=self.root),
            "dialogue": DialogueVerifier(root=self.root),
        }

    def policy_state(self):
        return policy_enforcement.policy_summary(root=self.root)

    def policy(self):
        from skeleton.organism.policy_control_card import policy_control_card
        return policy_control_card(root=self.root)

    def threshold(self, surface=""):
        from skeleton.organism.policy_card import threshold_card
        return threshold_card(root=self.root, surface=surface)

    def set_threshold(self, surface, value):
        from skeleton.organism.policy_card import set_threshold_card
        return set_threshold_card(surface, value, root=self.root)

    def set_repair_enabled(self, surface, enabled):
        from skeleton.organism.policy_card import set_repair_enabled_card
        return set_repair_enabled_card(surface, enabled, root=self.root)

    def set_repair_class(self, name, enabled):
        from skeleton.organism.policy_card import set_repair_class_card
        return set_repair_class_card(name, enabled, root=self.root)

    def policy_gate(self, surface, score):
        return policy_enforcement.gate_check(surface, score, root=self.root)

    def save_policy_version(self, *, comment="", author="system", **kwargs):
        return policy_versioning.save_version(root=self.root, comment=comment, author=author, **kwargs)

    def policy_versions(self, limit=4):
        return policy_versioning.version_card(root=self.root, limit=limit)

    def policy_diff(self, a, b):
        return policy_versioning.diff_versions(a, b, root=self.root)

    def policy_lineage(self, version):
        return policy_versioning.version_lineage(version, root=self.root)

    def rollback_preview(self, version):
        return rollback_preview(version, root=self.root)

    def policy_rollback(self, version):
        result = policy_versioning.rollback(version, root=self.root)
        self.audit.record("operator", "policy_rollback", "policy", {"version": version, "result": result})
        return result

    def repair_orchestrate(self, surface, trigger, *args, **kwargs):
        return orchestrated_repair(surface, trigger, *args, root=self.root, **kwargs)

    def repair_sessions(self, surface=""):
        return repair_autonomy.repair_session_card(surface, root=self.root)

    def repair_effectiveness(self, surface=""):
        return repair_autonomy.repair_effectiveness(surface, root=self.root)

    def repair_telemetry(self, surface=""):
        return repair_telemetry.telemetry_card(surface, root=self.root)

    def repair_errors(self, surface=""):
        return repair_telemetry.error_summary(surface, root=self.root)

    def repair_learned(self):
        return learned_repair.learned_policy_card(root=self.root)

    def repair_strategy(self, surface, reason):
        return learned_repair.suggest_repair_strategy(surface, reason, root=self.root)

    def verify_forge(self, files, **kwargs):
        return self.verifiers["forge"].verify(files, **kwargs).to_dict()

    def verify_plan(self, plan, **kwargs):
        return self.verifiers["plan"].verify(plan, **kwargs).to_dict()

    def verify_pipeline(self, spec, **kwargs):
        return self.verifiers["pipeline"].verify_game_logic(spec, **kwargs).to_dict()

    def verify_npc(self, spec, **kwargs):
        return self.verifiers["npc"].verify(spec, **kwargs).to_dict()

    def verify_dialogue(self, tree, **kwargs):
        return self.verifiers["dialogue"].verify(tree, **kwargs).to_dict()

    def lattice_hud(self):
        return lattice_card(self.hud_lattice)

    def lattice_editor(self):
        return lattice_card(self.editor_lattice)

    def steering_register(self, name, *, dims=None, strength=1.0):
        return self.steering.register(name, dims=dims, strength=strength).to_dict()

    def steering_activate(self, name, weight=1.0):
        self.steering.activate(name, weight)
        return self.steering_composite()

    def steering_deactivate(self, name):
        self.steering.deactivate(name)
        return self.steering_composite()

    def steering_composite(self):
        return {"vector": self.steering.composite_vector(), "card": self.steering.card()}

    def kv_cache_stats(self):
        return self.kv_cache.card()

    def mouth_feed(self, phoneme, timestamp_ms, confidence=1.0):
        return self.mouth.feed_phoneme(phoneme, timestamp_ms, confidence).to_dict()

    def mouth_current(self):
        return self.mouth.current().to_dict()

    def lora_card(self):
        return self.lora.card()

    def decoder_card(self):
        return self.decoder.card()

    def master_card(self):
        return {"kind": "command-deck-master", "policy": self.policy_state(),
                "steering": self.steering_composite(), "kv_cache": self.kv_cache_stats(),
                "mouth": self.mouth_current(), "lora": self.lora_card(),
                "decoder": self.decoder_card(), "lattice_hud": self.lattice_hud(),
                "lattice_editor": self.lattice_editor()}
