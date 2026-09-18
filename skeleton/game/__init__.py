"""Canonical game-domain contracts for Skeleton."""

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
    REPLAY_SCHEMA,
    REPLAY_SCHEMA_VERSION,
    GameReplayError,
    MechanicsReplay,
    ReplayComparison,
    ReplayMismatch,
    ReplayStep,
    ReplayTrace,
)

__all__ = [
    "AIBehaviorSpec",
    "CombatStyle",
    "CombatSystemSpec",
    "EconomySystemSpec",
    "GameMechanicsError",
    "GameMechanicsGenerator",
    "GameReplayError",
    "MechanicType",
    "MechanicsReplay",
    "ProgressionStyle",
    "ProgressionSystemSpec",
    "REPLAY_SCHEMA",
    "REPLAY_SCHEMA_VERSION",
    "ReplayComparison",
    "ReplayMismatch",
    "ReplayStep",
    "ReplayTrace",
]
