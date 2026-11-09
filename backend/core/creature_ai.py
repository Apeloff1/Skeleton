"""Deterministic creature AI inspired by Newmove2 fish behavior.

The source mixed React hooks, random decisions, sensory processing and movement.
This module keeps the useful state-machine/needs model while making decisions
seedable and engine-neutral for authoritative simulation and tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import math
import random
from typing import Iterable


class CreatureState(StrEnum):
    IDLE = "idle"
    SEEKING = "seeking"
    FLEEING = "fleeing"
    RESTING = "resting"
    CURIOUS = "curious"


@dataclass(frozen=True, slots=True)
class Stimulus:
    kind: str
    x: float
    y: float
    intensity: float = 1.0


@dataclass(slots=True)
class CreatureTraits:
    aggression: float = 0.3
    curiosity: float = 0.5
    caution: float = 0.4
    persistence: float = 0.5

    def __post_init__(self) -> None:
        for value in (self.aggression, self.curiosity, self.caution, self.persistence):
            if not 0 <= value <= 1:
                raise ValueError("creature traits must be between 0 and 1")


@dataclass(slots=True)
class Creature:
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    energy: float = 100.0
    hunger: float = 50.0
    state: CreatureState = CreatureState.IDLE
    max_speed: float = 5.0
    vision_range: float = 100.0
    traits: CreatureTraits = field(default_factory=CreatureTraits)
    target: Stimulus | None = None

    @staticmethod
    def _distance(x: float, y: float, stimulus: Stimulus) -> float:
        return math.hypot(stimulus.x - x, stimulus.y - y)

    def _visible(self, stimuli: Iterable[Stimulus]) -> list[Stimulus]:
        return [
            stimulus
            for stimulus in stimuli
            if self._distance(self.x, self.y, stimulus) <= self.vision_range
        ]

    def _select_target(self, candidates: list[Stimulus]) -> Stimulus | None:
        if not candidates:
            return None
        return min(candidates, key=lambda item: self._distance(self.x, self.y, item))

    def _steer_toward(self, stimulus: Stimulus, *, away: bool = False) -> None:
        dx = stimulus.x - self.x
        dy = stimulus.y - self.y
        length = math.hypot(dx, dy) or 1.0
        direction = -1.0 if away else 1.0
        self.vx = direction * dx / length * self.max_speed
        self.vy = direction * dy / length * self.max_speed

    def update(self, dt: float, stimuli: Iterable[Stimulus], *, seed: int | None = None) -> CreatureState:
        if dt <= 0:
            raise ValueError("dt must be positive")
        rng = random.Random(seed)
        speed = math.hypot(self.vx, self.vy)
        self.energy = max(0.0, self.energy - (0.01 + speed * 0.005) * dt)
        self.hunger = min(100.0, self.hunger + 0.02 * dt)
        visible = self._visible(stimuli)
        threats = [item for item in visible if item.kind in {"predator", "threat"}]
        food = [item for item in visible if item.kind in {"food", "bait", "lure"}]
        nearest_threat = self._select_target(threats)
        nearest_food = self._select_target(food)
        threat_level = 0.0
        if nearest_threat is not None:
            threat_level = nearest_threat.intensity * max(
                0.0,
                1.0 - self._distance(self.x, self.y, nearest_threat) / self.vision_range,
            )

        if threat_level > max(0.3, 0.8 - self.traits.caution):
            self.state = CreatureState.FLEEING
            self.target = nearest_threat
            self._steer_toward(nearest_threat, away=True)
        elif self.energy < 20:
            self.state = CreatureState.RESTING
            self.target = None
            self.vx *= max(0.0, 1.0 - dt * 2)
            self.vy *= max(0.0, 1.0 - dt * 2)
            self.energy = min(100.0, self.energy + 0.1 * dt)
        elif self.hunger > 70 and nearest_food is not None:
            self.state = CreatureState.SEEKING
            self.target = nearest_food
            self._steer_toward(nearest_food)
        elif nearest_food is not None and self.traits.curiosity > 0.5:
            self.state = CreatureState.CURIOUS
            self.target = nearest_food
            self._steer_toward(nearest_food)
            self.vx *= 0.55
            self.vy *= 0.55
        else:
            self.state = CreatureState.IDLE
            self.target = None
            if rng.random() < min(1.0, 0.1 * dt):
                angle = rng.random() * math.tau
                speed = self.max_speed * 0.25
                self.vx = math.cos(angle) * speed
                self.vy = math.sin(angle) * speed
            else:
                self.vx *= max(0.0, 1.0 - 0.4 * dt)
                self.vy *= max(0.0, 1.0 - 0.4 * dt)

        self.x += self.vx * dt
        self.y += self.vy * dt
        return self.state
