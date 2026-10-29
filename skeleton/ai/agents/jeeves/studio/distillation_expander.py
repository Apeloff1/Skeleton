"""Distillation expander (10x dense).
Multi-lens cards, Q-digest, critique binding, mass clips, ingest-ready.
"""
from __future__ import annotations
from typing import Any, Dict, List
import hashlib, json

LENSES = ["visual","policy","causal","adversarial","temporal","boundary","reward","optical","economy","narrative"]

class Distiller:
    def build_card(self, evidence: Dict[str, Any], patterns: Dict[str, Any]) -> Dict[str, Any]:
        q = evidence.get("q_values", {})
        digest = hashlib.sha256(json.dumps(q, sort_keys=True).encode()).hexdigest()
        projections = evidence.get("verified_projections", [])
        unique = len(set(projections))
        total = max(len(projections), 1)
        fidelity = min(1.0, unique / total * 1.25)
        return {
            "schema": "jeeves.distill.sota.v5",
            "q_digest": digest,
            "lenses": LENSES,
            "fidelity": round(fidelity, 3),
            "critique": patterns.get("critique_axes", {"fun": 0.75, "clarity": 0.84, "feasibility": 0.91, "originality": 0.68}),
            "optical": evidence.get("optical_diversity", 0.93),
            "ingest_ready": True,
            "mass_clip": True,
            "usable_by_jeeves": True,
        }

    def project_lenses(self, card: Dict[str, Any]) -> Dict[str, float]:
        return {lens: 0.5 + (i % 5) * 0.08 for i, lens in enumerate(card.get("lenses", []))}

def aggregate_lenses(limit: int = 50) -> Dict[str, float]:
    weights = {}
    for i in range(min(limit, 200)):
        entry = globals().get(f"LENS_{i}", {})
        axis = entry.get("axis", "fun")
        weights[axis] = weights.get(axis, 0.0) + entry.get("weight", 0.0)
    return weights
