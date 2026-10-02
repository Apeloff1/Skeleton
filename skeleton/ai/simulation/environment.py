"""Engine-neutral simulation environment and evidence boundary for P3."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Callable, Mapping


class SimulationBoundaryError(RuntimeError):
    pass


def _digest(value: object) -> str:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise SimulationBoundaryError("simulation value is not deterministic JSON") from exc
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _state(value: Mapping[str, object]) -> dict[str, object]:
    frozen = dict(value)
    _digest(frozen)
    if len(frozen) > 256:
        raise SimulationBoundaryError("simulation state exceeds field limit")
    return frozen


@dataclass(frozen=True, slots=True)
class SimulationEvidence:
    simulation_id: str
    step_index: int
    seed: int
    prior_state_digest: str
    action_digest: str
    next_state_digest: str
    uncertainty: float
    evidence_class: str = "simulation"

    def __post_init__(self) -> None:
        if not isinstance(self.simulation_id, str) or not self.simulation_id.strip():
            raise SimulationBoundaryError("simulation_id must be non-empty")
        if isinstance(self.step_index, bool) or not isinstance(self.step_index, int) or self.step_index < 0:
            raise SimulationBoundaryError("step_index must be non-negative")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise SimulationBoundaryError("seed must be integer")
        if not 0.0 <= float(self.uncertainty) <= 1.0:
            raise SimulationBoundaryError("uncertainty must be in [0, 1]")
        if self.evidence_class != "simulation":
            raise SimulationBoundaryError("rollouts are simulation evidence only")

    @property
    def can_support_real_world_fact(self) -> bool:
        return False

    def require_real_world_fact_authority(self) -> None:
        raise SimulationBoundaryError("simulation evidence cannot be promoted to real-world fact evidence")


@dataclass(frozen=True, slots=True)
class EnvironmentTransition:
    state: Mapping[str, object]
    reward: float
    terminal: bool
    evidence: SimulationEvidence


Reducer = Callable[
    [Mapping[str, object], Mapping[str, object], int],
    tuple[Mapping[str, object], float, bool, float],
]


class DeterministicEnvironmentAdapter:
    def __init__(
        self,
        *,
        simulation_id: str,
        initial_state: Mapping[str, object],
        reducer: Reducer,
        seed: int = 0,
    ) -> None:
        if not isinstance(simulation_id, str) or not simulation_id.strip():
            raise SimulationBoundaryError("simulation_id must be non-empty")
        if not callable(reducer):
            raise TypeError("reducer must be callable")
        self.simulation_id = simulation_id.strip()
        self.initial_state = _state(initial_state)
        self.reducer = reducer
        self.seed = seed
        self._state = dict(self.initial_state)
        self._step = 0

    @property
    def state(self) -> Mapping[str, object]:
        return dict(self._state)

    def reset(self) -> Mapping[str, object]:
        self._state = dict(self.initial_state)
        self._step = 0
        return self.state

    def step(self, action: Mapping[str, object]) -> EnvironmentTransition:
        action_payload = _state(action)
        prior = dict(self._state)
        next_state_raw, reward, terminal, uncertainty = self.reducer(prior, action_payload, self.seed)
        next_state = _state(next_state_raw)
        evidence = SimulationEvidence(
            simulation_id=self.simulation_id,
            step_index=self._step,
            seed=self.seed,
            prior_state_digest=_digest(prior),
            action_digest=_digest(action_payload),
            next_state_digest=_digest(next_state),
            uncertainty=float(uncertainty),
        )
        self._state = next_state
        self._step += 1
        return EnvironmentTransition(next_state, float(reward), bool(terminal), evidence)


__all__ = [
    "DeterministicEnvironmentAdapter",
    "EnvironmentTransition",
    "SimulationBoundaryError",
    "SimulationEvidence",
]
