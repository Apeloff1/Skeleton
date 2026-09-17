"""Deterministic AI behavior transitions. No learning. No wall clock."""

from __future__ import annotations

import hashlib
from typing import Any

from skeleton.game.mechanics import AIBehaviorSpec, GameMechanicsError


AI_STATES = ("idle", "patrol", "chase", "retreat", "extract")
MAX_AI_TICKS = 2_048


class AIPolicyError(GameMechanicsError):
    code = "GAME.AI_POLICY"


def _roll(seed: int, tick: int, entity: str) -> int:
    material = f"{seed}:{tick}:{entity}:ai".encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


def next_state(
    spec: AIBehaviorSpec,
    *,
    seed: int,
    tick: int,
    hp_ratio: float,
    heat_ratio: float,
    current: str = "idle",
) -> str:
    if not isinstance(spec, AIBehaviorSpec):
        raise AIPolicyError("spec must be AIBehaviorSpec")
    if current not in AI_STATES:
        raise AIPolicyError(f"unknown ai state: {current}")
    if tick < 0 or tick > MAX_AI_TICKS:
        raise AIPolicyError("ai tick out of range")
    if not 0.0 <= hp_ratio <= 1.0 or not 0.0 <= heat_ratio <= 1.0:
        raise AIPolicyError("ratios must be in [0, 1]")
    if hp_ratio <= 0.15 or heat_ratio >= 0.90:
        return "retreat"
    if hp_ratio >= 0.85 and heat_ratio <= 0.20 and spec.aggression_level < 0.25:
        return "extract"
    roll = _roll(int(seed), tick, spec.entity_type)
    threshold = int(spec.aggression_level * 100) + int(spec.intelligence_level * 20)
    if "chase" in spec.behaviors and (roll % 100) < threshold:
        return "chase"
    if "patrol" in spec.behaviors and (roll % 100) < 55:
        return "patrol"
    if current == "chase" and (roll % 100) < 30:
        return "patrol"
    return "idle" if current == "extract" else current


def run_policy(
    spec: AIBehaviorSpec,
    *,
    seed: int,
    ticks: int,
    hp_ratio: float = 0.7,
    heat_ratio: float = 0.2,
) -> list[dict[str, Any]]:
    if isinstance(ticks, bool) or not isinstance(ticks, int) or ticks < 1:
        raise AIPolicyError("ticks must be a positive integer")
    if ticks > MAX_AI_TICKS:
        raise AIPolicyError("too many ai ticks")
    state = "idle"
    frames = []
    for tick in range(ticks):
        state = next_state(
            spec,
            seed=seed,
            tick=tick,
            hp_ratio=hp_ratio,
            heat_ratio=heat_ratio,
            current=state,
        )
        frames.append({"t": tick, "entity": spec.entity_type, "state": state})
    return frames
