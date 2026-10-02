"""Provenance-bound local model lifecycle and migration control."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Mapping

from .native import ModelBillOfMaterials, TrainingEvaluation


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
    ).hexdigest()


class ModelLifecycleState(str, Enum):
    CANDIDATE="candidate"
    VALIDATED="validated"
    ACTIVE="active"
    DEPRECATED="deprecated"
    RETIRED="retired"


_ALLOWED={
    ModelLifecycleState.CANDIDATE:{ModelLifecycleState.VALIDATED},
    ModelLifecycleState.VALIDATED:{ModelLifecycleState.ACTIVE},
    ModelLifecycleState.ACTIVE:{ModelLifecycleState.DEPRECATED},
    ModelLifecycleState.DEPRECATED:{ModelLifecycleState.RETIRED},
    ModelLifecycleState.RETIRED:set(),
}


@dataclass(frozen=True, slots=True)
class LifecycleTransition:
    model_digest: str
    from_state: str
    to_state: str
    evidence_digest: str
    transition_digest: str


@dataclass(frozen=True, slots=True)
class ProviderMigrationDecision:
    source_model_digest: str
    target_model_digest: str
    parity_score: float
    required_score: float
    approved: bool
    rollback_model_digest: str
    evidence_digest: str

    @property
    def digest(self) -> str:
        return _digest({
            "source_model_digest":self.source_model_digest,
            "target_model_digest":self.target_model_digest,
            "parity_score":self.parity_score,
            "required_score":self.required_score,
            "approved":self.approved,
            "rollback_model_digest":self.rollback_model_digest,
            "evidence_digest":self.evidence_digest,
        })


class ModelLifecycleRegistry:
    def __init__(self) -> None:
        self._states: dict[str,ModelLifecycleState]={}
        self._mbom: dict[str,ModelBillOfMaterials]={}
        self._history: list[LifecycleTransition]=[]

    def register_candidate(self, mbom: ModelBillOfMaterials) -> None:
        digest=mbom.model_digest
        prior=self._mbom.get(digest)
        if prior is not None and prior.digest!=mbom.digest:
            raise ValueError("model digest cannot be rebound to different MBOM")
        self._mbom[digest]=mbom
        self._states.setdefault(digest,ModelLifecycleState.CANDIDATE)

    def state(self, model_digest: str) -> ModelLifecycleState:
        try:
            return self._states[model_digest]
        except KeyError as exc:
            raise KeyError("unknown model") from exc

    def transition(
        self,
        model_digest: str,
        to_state: ModelLifecycleState,
        *,
        evidence: Mapping[str,object],
        evaluation: TrainingEvaluation | None = None,
    ) -> LifecycleTransition:
        current=self.state(model_digest)
        if to_state not in _ALLOWED[current]:
            raise ValueError(f"illegal model lifecycle transition {current.value}->{to_state.value}")
        if not evidence:
            raise ValueError("lifecycle transition requires evidence")
        if to_state in {ModelLifecycleState.VALIDATED,ModelLifecycleState.ACTIVE}:
            if evaluation is None or not evaluation.passed or evaluation.model_digest!=model_digest:
                raise ValueError("validation/activation requires passing model evaluation")
        evidence_digest=_digest(dict(evidence))
        transition_digest=_digest({
            "model":model_digest,"from":current.value,"to":to_state.value,
            "evidence":evidence_digest,"mbom":self._mbom[model_digest].digest,
        })
        receipt=LifecycleTransition(
            model_digest=model_digest,
            from_state=current.value,
            to_state=to_state.value,
            evidence_digest=evidence_digest,
            transition_digest=transition_digest,
        )
        self._states[model_digest]=to_state
        self._history.append(receipt)
        return receipt

    def migration_decision(
        self,
        *,
        source_model_digest: str,
        target_model_digest: str,
        parity_score: float,
        required_score: float,
        evidence: Mapping[str,object],
    ) -> ProviderMigrationDecision:
        if self.state(source_model_digest) is not ModelLifecycleState.ACTIVE:
            raise ValueError("migration source must be active")
        if self.state(target_model_digest) is not ModelLifecycleState.VALIDATED:
            raise ValueError("migration target must be validated before cutover")
        if not 0.0<=parity_score<=1.0 or not 0.0<=required_score<=1.0:
            raise ValueError("parity scores must be in [0, 1]")
        if not evidence:
            raise ValueError("migration requires evidence")
        return ProviderMigrationDecision(
            source_model_digest=source_model_digest,
            target_model_digest=target_model_digest,
            parity_score=parity_score,
            required_score=required_score,
            approved=parity_score>=required_score,
            rollback_model_digest=source_model_digest,
            evidence_digest=_digest(dict(evidence)),
        )

    @property
    def history(self) -> tuple[LifecycleTransition,...]:
        return tuple(self._history)
