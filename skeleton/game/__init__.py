"""Canonical game-domain contracts for Skeleton."""

from .clock import ClockError, GameClock, MAX_TICKS
from .engine import ALLOWED_VERBS, DeterministicEngine, EngineError, WorldState
from .mechanics import (
    AIBehaviorSpec,
    CombatStyle,
    CombatSystemSpec,
    EconomySystemSpec,
    GameMechanicsError,
    GameMechanicsGenerator,
    MechanicType,
    ProgressionStyle,
    ProgressionSystemSpec,
)
from .replay import (
    REPLAY_KIND,
    REPLAY_SCHEMA_VERSION,
    ReplayError,
    ReplayTrace,
    compare,
    load_trace,
    record,
    replay,
    verify,
)

__all__ = [
    "ALLOWED_VERBS",
    "AIBehaviorSpec",
    "ClockError",
    "CombatStyle",
    "CombatSystemSpec",
    "DeterministicEngine",
    "EconomySystemSpec",
    "EngineError",
    "GameClock",
    "GameMechanicsError",
    "GameMechanicsGenerator",
    "MAX_TICKS",
    "MechanicType",
    "ProgressionStyle",
    "ProgressionSystemSpec",
    "REPLAY_KIND",
    "REPLAY_SCHEMA_VERSION",
    "ReplayError",
    "ReplayTrace",
    "WorldState",
    "compare",
    "load_trace",
    "record",
    "replay",
    "verify",
]
