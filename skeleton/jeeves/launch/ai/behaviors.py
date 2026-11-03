"""Launch-ready AI behavior and decision system.

Real, immediately usable decision trees and behavior selection
for enemies, bosses, and player AI. No stubs.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from enum import Enum


class Action(str, Enum):
    IDLE = "idle"
    PATROL = "patrol"
    CHASE = "chase"
    ATTACK = "attack"
    FLEE = "flee"
    HEAL = "heal"
    SUMMON = "summon"
    ENRAGE = "enrage"


class BehaviorSelector:
    """Selects an action given threat, health, and distance."""

    def select(self, health: float, threat: float, distance: float = 5.0, phase: int = 1) -> Action:
        if health <= 0:
            return Action.IDLE
        if health < 0.2:
            return Action.FLEE if threat > 0.5 else Action.HEAL
        if phase >= 3 and health < 0.4:
            return Action.ENRAGE
        if distance < 2.0 and threat > 0.4:
            return Action.ATTACK
        if threat > 0.7:
            return Action.CHASE
        if distance > 8.0:
            return Action.PATROL
        return Action.IDLE


class BossPhaseController:
    """Manages multi-phase boss transitions."""

    def __init__(self, phases: int = 3) -> None:
        self.phases = phases
        self.current = 1
        self._thresholds = [1.0 - (i / phases) for i in range(phases)]

    def update(self, health_ratio: float) -> Dict[str, Any]:
        new_phase = self.current
        for i, thresh in enumerate(self._thresholds):
            if health_ratio <= thresh:
                new_phase = i + 1
        transitioned = new_phase != self.current
        self.current = new_phase
        return {
            "phase": self.current,
            "transitioned": transitioned,
            "mechanic": self._mechanic_for(self.current),
            "enraged": self.current >= self.phases,
        }

    def _mechanic_for(self, phase: int) -> str:
        return ["slam", "summon", "enrage", "ultimate"][min(phase - 1, 3)]


class PlayerAIAssist:
    """Lightweight assist suggestions for the player character."""

    def suggest(self, health: float, ammo: int = 10, nearby_enemies: int = 0) -> Dict[str, Any]:
        if health < 0.3:
            return {"action": "heal_or_retreat", "priority": "high"}
        if nearby_enemies >= 3 and ammo < 3:
            return {"action": "reposition", "priority": "medium"}
        if nearby_enemies > 0:
            return {"action": "engage", "priority": "normal"}
        return {"action": "explore", "priority": "low"}


class CombatResolver:
    """Resolves a single combat exchange."""

    def resolve(self, attacker_damage: int, defender_health: int, defender_armor: int = 0) -> Dict[str, Any]:
        mitigated = max(0, attacker_damage - defender_armor)
        new_health = max(0, defender_health - mitigated)
        return {
            "damage_dealt": mitigated,
            "defender_health": new_health,
            "killed": new_health <= 0,
        }
