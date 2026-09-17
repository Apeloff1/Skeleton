"""Canonical game-domain contracts for Skeleton."""

from .ai_policy import AIPolicyError, next_state, run_policy
from .arena import ArenaError, run_arena
from .clock import MAX_TICKS, ClockError, GameClock
from .doctor import DoctorError, doctor
from .emit_pack import EmitPackError, default_tree, validate_emit
from .flake import FlakeError, advance, ledger, open_flake
from .release_graph import ReleaseGraphError, graph as release_graph
from .spec import SpecError, compile_spec
from .token_clock import TokenClockError, tick as token_tick
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
    "DoctorError",
    "EmitPackError",
    "FlakeError",
    "ReleaseGraphError",
    "SpecError",
    "TokenClockError",
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
    "advance",
    "compile_intent",
    "compile_spec",
    "critique",
    "default_tree",
    "doctor",
    "execute",
    "ledger",
    "open_flake",
    "release_graph",
    "token_tick",
    "validate_emit",
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
