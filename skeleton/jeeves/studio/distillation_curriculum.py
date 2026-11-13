"""Distillation curricula (creative longform).
Multi-step training plans from episodes: warm-up, core loop, boss phase, cutscene, critique.
"""
from __future__ import annotations
from typing import Any, Dict, List
import hashlib, json

class DistillationCurriculum:
    def build(self, evidence: Dict[str, Any], patterns: Dict[str, Any]) -> Dict[str, Any]:
        steps = [
            {"name": "warmup", "focus": "movement", "steps": 20, "target_fidelity": 0.85},
            {"name": "core_loop", "focus": "clear_packs_spend", "steps": 60, "target_fidelity": 0.92},
            {"name": "enemy_engage", "focus": "combat", "steps": 40, "target_fidelity": 0.90},
            {"name": "boss_phases", "focus": "phase_transitions", "steps": 50, "target_fidelity": 0.93},
            {"name": "cutscene", "focus": "narrative_branch", "steps": 15, "target_fidelity": 0.88},
        ]
        q = evidence.get("q_values", {})
        digest = hashlib.sha256(json.dumps(q, sort_keys=True).encode()).hexdigest()[:16]
        return {
            "schema": "jeeves.curriculum.v1",
            "steps": steps,
            "q_digest": digest,
            "optical": evidence.get("optical_diversity", 0.93),
            "critique": patterns.get("critique_axes", {}),
            "ingest_ready": True,
            "total_steps": sum(s["steps"] for s in steps),
        }
