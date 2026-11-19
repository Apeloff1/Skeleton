"""Deterministic bounded Prood planning contract.

A plan describes proposed work, not actual agent admission, execution or
resource qualification. No provider, global database, or network is used.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from skeleton.frontier.payloads import json_snapshot

_CATEGORIES = {
    "world": "world", "narrative": "narrative", "mechanics": "systems",
    "procedural": "procgen", "tileset": "visual_design", "assets": "art",
}
_MAX_PHASES = 128
_MAX_WORKERS = 1024


def _identity(value: str, name: str) -> str:
    if type(value) is not str or not 1 <= len(value) <= 128 or value != value.strip():
        raise ValueError(f"invalid {name}")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(f"invalid {name}")
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False,
    ).encode("utf-8")).hexdigest()


def plan_build(
    build_id: str,
    phases: list[str] | None = None,
    seed: int = 0,
    platoon_size: int = 5,
    game_ctx: dict | None = None,
    **kwargs: Any,
) -> dict:
    build_id = _identity(build_id, "build identity")
    if kwargs:
        raise ValueError("unknown planning options")
    if type(seed) is not int or not -(1 << 63) <= seed < (1 << 63):
        raise ValueError("invalid seed")
    if type(platoon_size) is not int or not 1 <= platoon_size <= 12:
        raise ValueError("invalid platoon size")
    if phases is None:
        phases = []
    if type(phases) is not list or len(phases) > _MAX_PHASES:
        raise ValueError("invalid phase inventory")
    phase_list = [_identity(phase, "phase identity") for phase in phases]
    if len(set(phase_list)) != len(phase_list):
        raise ValueError("duplicate phase identity")
    if len(phase_list) * platoon_size > _MAX_WORKERS:
        raise ValueError("worker budget exceeded")
    if game_ctx is not None and type(game_ctx) is not dict:
        raise ValueError("invalid game context")
    context_digest = _digest(json_snapshot(game_ctx or {}, max_bytes=262144))
    identity = {
        "schema": "prood.plan.v2", "build_id": build_id, "seed": seed,
        "phases": phase_list, "platoon_size": platoon_size,
        "context_digest": context_digest,
    }
    plan_hash = _digest(identity)
    nodes = []
    for index, phase in enumerate(phase_list):
        workers = []
        for seat in range(platoon_size):
            worker_identity = _digest([plan_hash, index, seat])
            workers.append({
                "code": "W" + worker_identity[:24],
                "agent": f"Worker-{index}-{seat}",
                "category": _CATEGORIES.get(phase, "world"),
                "team_seat": seat + 1,
                "admitted": False,
            })
        nodes.append({"phase_id": phase, "tier": "platoon", "workers": workers})
    return {
        "plan_hash": plan_hash, "nodes": nodes, "build_id": build_id, "seed": seed,
        "context_digest": context_digest, "status": "planned_only",
        "worker_count": len(phase_list) * platoon_size,
        "execution_verified": False,
    }
