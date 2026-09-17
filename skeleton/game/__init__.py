"""Canonical game-domain contracts for Skeleton."""

from .ai_policy import AIPolicyError, next_state, run_policy
from .clock import MAX_TICKS, ClockError, GameClock
from .engine import ALLOWED_VERBS, DeterministicEngine, EngineError, WorldState
from .era_bind import HOUSE_ERA, EraBindError, bind_era
from .harbor import Harbor, HarborError
from .mass import MassError, clip_mass, observe_mass, trajectory
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
from .pack import PackError, validate_pack
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
from .session import SESSION_KIND, run_session

__all__ = [
    "ALLOWED_VERBS",
    "AIBehaviorSpec",
    "AIPolicyError",
    "ClockError",
    "CombatStyle",
    "CombatSystemSpec",
    "DeterministicEngine",
    "EconomySystemSpec",
    "EngineError",
    "EraBindError",
    "GameClock",
    "GameMechanicsError",
    "GameMechanicsGenerator",
    "HOUSE_ERA",
    "Harbor",
    "HarborError",
    "MAX_TICKS",
    "MassError",
    "MechanicType",
    "PackError",
    "ProgressionStyle",
    "ProgressionSystemSpec",
    "REPLAY_KIND",
    "REPLAY_SCHEMA_VERSION",
    "ReplayError",
    "ReplayTrace",
    "SESSION_KIND",
    "WorldState",
    "bind_era",
    "clip_mass",
    "compare",
    "load_trace",
    "next_state",
    "observe_mass",
    "record",
    "replay",
    "run_policy",
    "run_session",
    "trajectory",
    "validate_pack",
    "verify",
]
