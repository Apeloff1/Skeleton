from dataclasses import dataclass

@dataclass(frozen=True)
class ModelGovernanceEvidence:
    evidence_id: str
    owner: str
    rollback: str
    retention: str

@dataclass(frozen=True)
class ModelLifecycle:
    model_id: str
    state: str
    evidence: tuple[ModelGovernanceEvidence, ...]

@dataclass(frozen=True)
class ModelTransition:
    source: str
    target: str
    evidence_id: str

_ALLOWED = {"intake":{"training"},"training":{"evaluation"},"evaluation":{"deployment"},"deployment":{"operation"},"operation":{"update","retirement"},"update":{"evaluation","operation"},"retirement":{"archive"}}

def transition(m, target, e):
    if not m.model_id or m.state not in _ALLOWED or not e.evidence_id:
        raise ValueError("valid model/evidence identity required")
    if any(x.evidence_id == e.evidence_id for x in m.evidence):
        raise ValueError("duplicate governance evidence")
    if target not in _ALLOWED.get(m.state, set()):
        raise ValueError("invalid model lifecycle transition")
    if not e.owner or not e.rollback or not e.retention:
        raise ValueError("governance evidence incomplete")
    return ModelLifecycle(m.model_id, target, m.evidence + (e,))
