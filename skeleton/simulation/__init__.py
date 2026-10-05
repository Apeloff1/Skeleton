"""Engine-neutral deterministic simulation primitives."""

from . import ecs, physics
from .environment import (
    DeterministicEnvironmentAdapter,
    EnvironmentTransition,
    SimulationBoundaryError,
    SimulationEvidence,
)
from .authority import (
    RolloutRequest,
    SimulationAuthorityError,
    SimulationAuthorityGuard,
    SimulationPermit,
    SimulationResourceBudget,
)
from .world import SimulationAction, WorldRule, WorldRules
from .world_model import (
    Assumption,
    AssumptionSet,
    CounterfactualResult,
    CounterfactualRolloutEngine,
    EnvironmentAdapter,
    SimulationResult,
    SimulationStep,
    UncertaintyPropagationPolicy,
    WorldModelError,
    WorldState,
)

__all__ = [
    "ecs",
    "physics",
    "DeterministicEnvironmentAdapter",
    "EnvironmentTransition",
    "SimulationBoundaryError",
    "SimulationEvidence",
    "RolloutRequest",
    "SimulationAuthorityError",
    "SimulationAuthorityGuard",
    "SimulationPermit",
    "SimulationResourceBudget",
    "SimulationAction",
    "WorldRule",
    "WorldRules",
    "Assumption",
    "AssumptionSet",
    "CounterfactualResult",
    "CounterfactualRolloutEngine",
    "EnvironmentAdapter",
    "SimulationResult",
    "SimulationStep",
    "UncertaintyPropagationPolicy",
    "WorldModelError",
    "WorldState",
]
