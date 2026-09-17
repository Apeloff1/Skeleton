"""Canonical game-domain contracts for Skeleton."""

from .ai_policy import AIPolicyError, next_state, run_policy
from .arena import ArenaError, run_arena
from .clock import MAX_TICKS, ClockError, GameClock
from .conductor import STEPS, ConductorError, execute
from .critique import CritiqueError, critique, improve, monte_carlo
from .engine import ALLOWED_VERBS, DeterministicEngine, EngineError, WorldState
from .era_bind import HOUSE_ERA, EraBindError, bind_era
from .harbor import Harbor, HarborError
from .intent import IntentError, compile_intent
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
from .world_graph import WorldGraphError, place, walk

__all__ = [
    "ALLOWED_VERBS",
    "AIBehaviorSpec",
    "AIPolicyError",
    "ArenaError",
    "ClockError",
    "CombatStyle",
    "CombatSystemSpec",
    "ConductorError",
    "CritiqueError",
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
    "IntentError",
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
    "STEPS",
    "WorldGraphError",
    "WorldState",
    "bind_era",
    "clip_mass",
    "compare",
    "compile_intent",
    "critique",
    "execute",
    "improve",
    "load_trace",
    "monte_carlo",
    "next_state",
    "observe_mass",
    "place",
    "record",
    "replay",
    "run_arena",
    "run_policy",
    "run_session",
    "trajectory",
    "validate_pack",
    "verify",
    "walk",
]
