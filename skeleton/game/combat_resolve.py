"""Deterministic combat resolver. Status, magic, party. No wall clock."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from skeleton.game.mechanics import CombatStyle, CombatSystemSpec


MAX_ROUNDS = 32
STATUSES = ("poison", "burn", "freeze", "stun")


class CombatResolveError(ValueError):
    """Combat resolver contract violation."""


def _roll(seed: int, round_i: int, lane: str) -> int:
    material = f"{int(seed)}:{round_i}:{lane}:cbt".encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


def _unit(name: str, hp: int, atk: int) -> dict[str, Any]:
    if hp < 1 or atk < 0:
        raise CombatResolveError("unit stats invalid")
    return {"name": name, "hp": hp, "atk": atk, "defending": False, "status": "", "ticks": 0}


def _apply_status(unit: dict[str, Any]) -> None:
    status = unit["status"]
    if not status:
        return
    if status == "poison":
        unit["hp"] = max(0, unit["hp"] - 5)
    elif status == "burn":
        unit["hp"] = max(0, unit["hp"] - 8)
    unit["ticks"] = max(0, int(unit["ticks"]) - 1)
    if unit["ticks"] <= 0:
        unit["status"] = ""


def _hit(seed: int, round_i: int, attacker: dict[str, Any], defender: dict[str, Any], spec: CombatSystemSpec) -> int:
    roll = _roll(seed, round_i, attacker["name"])
    dmg = attacker["atk"] + (roll % 5)
    if spec.include_magic:
        dmg += 1
    if defender["defending"]:
        dmg = max(0, dmg - 3)
    if spec.style == CombatStyle.TACTICAL:
        dmg = int(dmg * 1.15) if roll % 4 == 0 else dmg
    if roll % 20 == 0:
        dmg *= 2
    defender["hp"] = max(0, defender["hp"] - dmg)
    if spec.include_status_effects and roll % 7 == 0:
        defender["status"] = STATUSES[roll % len(STATUSES)]
        defender["ticks"] = 2
    return dmg


def resolve(
    *,
    seed: int,
    spec: CombatSystemSpec | None = None,
    player_hp: int = 40,
    enemy_hp: int = 30,
    rounds: int = 8,
) -> dict[str, Any]:
    if rounds < 1 or rounds > MAX_ROUNDS:
        raise CombatResolveError("rounds out of range")
    spec = spec or CombatSystemSpec(style=CombatStyle.TURN_BASED)
    player = _unit("player", player_hp, 6)
    enemy = _unit("enemy", enemy_hp, 5)
    frames: list[dict[str, Any]] = []
    for index in range(rounds):
        _apply_status(player)
        _apply_status(enemy)
        if player["hp"] <= 0 or enemy["hp"] <= 0:
            break
        verb_roll = _roll(seed, index, "verb")
        player["defending"] = verb_roll % 5 == 0
        dealt = 0 if player["defending"] or player["status"] in {"freeze", "stun"} else _hit(seed, index, player, enemy, spec)
        taken = 0
        if enemy["hp"] > 0 and enemy["status"] not in {"freeze", "stun"}:
            taken = _hit(seed, index, enemy, player, spec)
        frames.append({
            "t": index,
            "player_hp": player["hp"],
            "enemy_hp": enemy["hp"],
            "dealt": dealt,
            "taken": taken,
            "status_p": player["status"],
            "status_e": enemy["status"],
        })
    winner = "draw"
    if player["hp"] > enemy["hp"]:
        winner = "player"
    elif enemy["hp"] > player["hp"]:
        winner = "enemy"
    return {
        "kind": "combat_resolve",
        "seed": int(seed),
        "style": spec.style.value,
        "rounds": len(frames),
        "frames": frames,
        "player_hp": player["hp"],
        "enemy_hp": enemy["hp"],
        "winner": winner,
        "stored_prose": 0,
    }


def party_resolve(seed: int, members: list[Mapping[str, Any]], enemy_hp: int = 60) -> dict[str, Any]:
    if not members or len(members) > 4:
        raise CombatResolveError("party size 1..4")
    spec = CombatSystemSpec(style=CombatStyle.TURN_BASED, party_based=True)
    hp = sum(int(member.get("hp") or 20) for member in members)
    run = resolve(seed=seed, spec=spec, player_hp=hp, enemy_hp=enemy_hp, rounds=12)
    run["kind"] = "party_resolve"
    run["party"] = len(members)
    return run
