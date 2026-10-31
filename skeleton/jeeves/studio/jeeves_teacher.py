"""Jeeves teaching layer (10x).
Verb registry, example episodes, distillation ingest, operate instructions.
"""
from __future__ import annotations
from typing import Any, Dict, List

class JeevesTeacher:
    VERBS = [
        "studio-pipeline",
        "emit-world",
        "run-economy-chain",
        "advance-narrative",
        "sequence-boss",
        "distill-episode",
        "validate-pack",
        "critique-axes",
        "ingest-card",
    ]

    def teach(self) -> Dict[str, Any]:
        return {
            "verbs": self.VERBS,
            "example": "studio.run_full_pipeline(brief) -> pack + distill card",
            "ingest": "Jeeves.autoload.ingest(distill.json)",
            "fail_closed": "raise on fidelity < 0.92 or rights missing",
            "era": "HOUSE_ERA",
        }

    def example_episode(self) -> Dict[str, Any]:
        return {
            "brief": "Ash tunnels. Clear, salvage, multi-phase boss, cutscene.",
            "steps": 160,
            "reward_sum": 6.4,
            "optical_diversity": 0.94,
            "verified_projections": ["p1", "p2", "p3", "p4", "p5"],
            "core_loop": "clear_packs_spend_salvage",
        }
