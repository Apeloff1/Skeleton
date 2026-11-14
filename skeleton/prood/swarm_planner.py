"""Minimal swarm_planner stub for item_foundry (deterministic platoon plan).

Prood's full hierarchical planner depends on swarm_agents catalogs; this
stub preserves the ``plan_build`` contract item_foundry needs:
``{"plan_hash", "nodes": [{phase_id, tier, workers}]}``.
"""
from __future__ import annotations

import hashlib
from typing import Any


def plan_build(
    build_id: str,
    phases: list[str] | None = None,
    seed: int = 0,
    platoon_size: int = 5,
    game_ctx: dict | None = None,
    **_kwargs: Any,
) -> dict:
    phases = list(phases or [])
    platoon_size = max(1, min(int(platoon_size), 12))
    nodes: list[dict] = []
    for phase in phases:
        workers = [
            {
                "code": f"W{seed:02d}{i:02d}{phase[:3].upper()}",
                "agent": f"Worker-{phase}-{i}",
                "category": {
                    "world": "world", "narrative": "narrative",
                    "mechanics": "systems", "procedural": "procgen",
                    "tileset": "visual_design", "assets": "art",
                }.get(phase, "world"),
                "team_seat": i + 1,
            }
            for i in range(platoon_size)
        ]
        nodes.append({
            "phase_id": phase, "tier": "platoon", "workers": workers,
        })
    raw = f"{build_id}|{seed}|{','.join(phases)}|{platoon_size}"
    return {
        "plan_hash": hashlib.sha256(raw.encode()).hexdigest(),
        "nodes": nodes,
        "build_id": build_id,
        "seed": seed,
    }
