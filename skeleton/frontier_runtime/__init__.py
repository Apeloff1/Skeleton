"""Authoritative frontier fixed-step runtime.

Calls the existing Jeeves reference solvers and the registered engine-era
catalogue. It does not start a second physics engine or a native renderer.
"""

from skeleton.frontier_runtime.chunks import verify_dual_chunks
from skeleton.frontier_runtime.contacts import discrete_sphere_tunnels
from skeleton.frontier_runtime.eras import EraSolver, discover_era_solvers, era_solver
from skeleton.frontier_runtime.godot_delta import GODOT_SCENE, GODOT_SCRIPT
from skeleton.frontier_runtime.state import (
    ActorState,
    AirBody,
    CharacterBody,
    EnvironmentBody,
    MicroclimateState,
    SoftBodyState,
    StepRejected,
    StructureBody,
    TractionBody,
    WallState,
    WeatherState,
    WorldState,
)
from skeleton.frontier_runtime.step import (
    AuthoritativeRuntime,
    StepReceipt,
    replay_stream,
    verify_stream,
)

__all__ = [
    "GODOT_SCENE",
    "GODOT_SCRIPT",
    "ActorState",
    "AirBody",
    "AuthoritativeRuntime",
    "CharacterBody",
    "EnvironmentBody",
    "EraSolver",
    "MicroclimateState",
    "SoftBodyState",
    "StepReceipt",
    "StepRejected",
    "StructureBody",
    "TractionBody",
    "WallState",
    "WeatherState",
    "WorldState",
    "discover_era_solvers",
    "discrete_sphere_tunnels",
    "era_solver",
    "replay_stream",
    "verify_dual_chunks",
    "verify_stream",
]
