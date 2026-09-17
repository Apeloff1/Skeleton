"""Canonical game-domain contracts for Skeleton."""

from .ai_policy import AIPolicyError, next_state, run_policy
from .approval import ApprovalError, require, stamp
from .arena import ArenaError, run_arena
from .build_report import report as build_report
from .clock import MAX_TICKS, ClockError, GameClock
from .compose import compose
from .cut import CutError, cut, plan_sees
from .doctor import DoctorError, doctor
from .emit_pack import EmitPackError, default_tree, validate_emit
from .encounters import EncounterError, pack_tables
from .flake import FlakeError, advance, ledger, open_flake
from .handoff import HandoffError, offer, resolve
from .questionnaire import QuestionnaireError, fill
from .release_graph import ReleaseGraphError, graph as release_graph
from .spec import SpecError, compile_spec
from .token_clock import TokenClockError, tick as token_tick
from .turn_engine import TurnEngineError, play
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
    "ApprovalError",
    "ArenaError",
    "CutError",
    "DoctorError",
    "EmitPackError",
    "EncounterError",
    "FlakeError",
    "HandoffError",
    "QuestionnaireError",
    "ReleaseGraphError",
    "SpecError",
    "TokenClockError",
    "TurnEngineError",
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
    "build_report",
    "clip_mass",
    "compare",
    "compose",
    "cut",
    "advance",
    "compile_intent",
    "compile_spec",
    "critique",
    "default_tree",
    "doctor",
    "execute",
    "fill",
    "ledger",
    "offer",
    "open_flake",
    "pack_tables",
    "plan_sees",
    "play",
    "release_graph",
    "require",
    "resolve",
    "stamp",
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
