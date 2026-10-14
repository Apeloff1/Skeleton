from dataclasses import dataclass


@dataclass(frozen=True)
class ModelGovernanceEvidence:
    evidence_id: str
    owner: str
    rollback: str
    retention: str

    def __post_init__(self) -> None:
        if not all((self.evidence_id, self.owner, self.rollback, self.retention)):
            raise ValueError("governance evidence incomplete")


@dataclass(frozen=True)
class ModelLifecycle:
    model_id: str
    state: str
    evidence: tuple[ModelGovernanceEvidence, ...]

    def __post_init__(self) -> None:
        if not self.model_id or not self.state:
            raise ValueError("model lifecycle identity required")
        if any(not isinstance(item, ModelGovernanceEvidence) for item in self.evidence):
            raise ValueError("model governance evidence required")
        ids = [item.evidence_id for item in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate governance evidence")


@dataclass(frozen=True)
class ModelTransition:
    source: str
    target: str
    evidence_id: str


_ALLOWED = {
    "intake": {"training"},
    "training": {"evaluation"},
    "evaluation": {"deployment"},
    "deployment": {"operation"},
    "operation": {"update", "retirement"},
    "update": {"evaluation", "operation"},
    "retirement": {"archive"},
    "archive": set(),
}


def transition_with_receipt(
    lifecycle: ModelLifecycle,
    target: str,
    evidence: ModelGovernanceEvidence,
) -> tuple[ModelLifecycle, ModelTransition]:
    if (
        not isinstance(lifecycle, ModelLifecycle)
        or lifecycle.state not in _ALLOWED
        or not isinstance(evidence, ModelGovernanceEvidence)
    ):
        raise ValueError("valid model/evidence identity required")
    if evidence.evidence_id in {item.evidence_id for item in lifecycle.evidence}:
        raise ValueError("duplicate governance evidence")
    if target not in _ALLOWED[lifecycle.state]:
        raise ValueError("invalid model lifecycle transition")

    updated = ModelLifecycle(
        lifecycle.model_id,
        target,
        lifecycle.evidence + (evidence,),
    )
    receipt = ModelTransition(
        lifecycle.state,
        target,
        evidence.evidence_id,
    )
    return updated, receipt


def transition(
    lifecycle: ModelLifecycle,
    target: str,
    evidence: ModelGovernanceEvidence,
) -> ModelLifecycle:
    updated, _ = transition_with_receipt(lifecycle, target, evidence)
    return updated
