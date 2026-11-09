"""Admission matrix — AdaptiveGate × ChaosGovernor × verb (gf-server admit_write)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from skeleton.kernel.adaptive_gate import AdaptiveGate, Verdict
from skeleton.kernel.chaos import ChaosGovernor, Rung


class AdmissionOutcome(str, Enum):
    ADMIT = "admit"
    SHED = "shed"
    EMERGENCY_READ_ONLY = "emergency_read_only"
    SEAL_REQUIRED = "seal_required"
    OPEN_BYPASS = "open_bypass"


@dataclass(frozen=True)
class AdmissionDecision:
    outcome: AdmissionOutcome
    attester: Optional[str]
    priority: int
    rung: str
    tokens_note: str
    reason: str

    def as_dict(self) -> Dict[str, object]:
        return {
            "outcome": self.outcome.value,
            "attester": self.attester,
            "priority": self.priority,
            "rung": self.rung,
            "tokens_note": self.tokens_note,
            "reason": self.reason,
        }


@dataclass
class AdmissionMatrix:
    """Reusable evaluator; inject gate/governor for tests."""

    gate: AdaptiveGate = field(default_factory=lambda: AdaptiveGate(256, 128))
    governor: ChaosGovernor = field(default_factory=ChaosGovernor)
    open_prefixes: Tuple[str, ...] = (
        "/health",
        "/ready",
        "/api/v1/health",
        "/metrics",
        "/",
    )

    def is_open(self, path: str) -> bool:
        p = path or "/"
        for pref in self.open_prefixes:
            if pref == "/":
                if p == "/":
                    return True
                continue
            if p == pref or p.startswith(pref.rstrip("/") + "/") or p.startswith(pref):
                return True
        return False


def evaluate_admission(
    *,
    path: str,
    method: str,
    attester: Optional[str],
    priority: int = 1,
    matrix: Optional[AdmissionMatrix] = None,
) -> AdmissionDecision:
    """Mirror WriteAdmit + seal policy as a pure decision (no ASGI)."""
    m = matrix or AdmissionMatrix()
    meth = (method or "GET").upper()
    if m.is_open(path):
        return AdmissionDecision(
            outcome=AdmissionOutcome.OPEN_BYPASS,
            attester=attester,
            priority=priority,
            rung=m.governor.rung().name(),
            tokens_note="n/a",
            reason="open_probe",
        )
    if not attester:
        return AdmissionDecision(
            outcome=AdmissionOutcome.SEAL_REQUIRED,
            attester=None,
            priority=priority,
            rung=m.governor.rung().name(),
            tokens_note="n/a",
            reason="missing_attester",
        )
    mutating = meth in {"POST", "PUT", "PATCH", "DELETE"}
    if not mutating:
        return AdmissionDecision(
            outcome=AdmissionOutcome.ADMIT,
            attester=attester,
            priority=priority,
            rung=m.governor.rung().name(),
            tokens_note="read_path",
            reason="safe_method",
        )
    verdict = m.gate.admit(priority)
    if verdict is Verdict.SHED:
        m.governor.observe(False)
        return AdmissionDecision(
            outcome=AdmissionOutcome.SHED,
            attester=attester,
            priority=priority,
            rung=m.governor.rung().name(),
            tokens_note="shed",
            reason="adaptive_gate_shed",
        )
    if not m.governor.permits_writes():
        return AdmissionDecision(
            outcome=AdmissionOutcome.EMERGENCY_READ_ONLY,
            attester=attester,
            priority=priority,
            rung=m.governor.rung().name(),
            tokens_note="emergency",
            reason="chaos_emergency_read_only",
        )
    return AdmissionDecision(
        outcome=AdmissionOutcome.ADMIT,
        attester=attester,
        priority=priority,
        rung=m.governor.rung().name(),
        tokens_note="admitted",
        reason="ok",
    )


# --- generated route evaluators (Pack B coverage) ---

def admit_forge_get(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit GET /api/v1/forge/resource."""
    return evaluate_admission(path="/api/v1/forge/resource", method="GET", attester=attester, matrix=matrix)

def admit_forge_post(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit POST /api/v1/forge/resource."""
    return evaluate_admission(path="/api/v1/forge/resource", method="POST", attester=attester, matrix=matrix)

def admit_forge_put(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PUT /api/v1/forge/resource."""
    return evaluate_admission(path="/api/v1/forge/resource", method="PUT", attester=attester, matrix=matrix)

def admit_forge_patch(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PATCH /api/v1/forge/resource."""
    return evaluate_admission(path="/api/v1/forge/resource", method="PATCH", attester=attester, matrix=matrix)

def admit_forge_delete(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit DELETE /api/v1/forge/resource."""
    return evaluate_admission(path="/api/v1/forge/resource", method="DELETE", attester=attester, matrix=matrix)

def admit_gameforge_get(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit GET /api/v1/gameforge/resource."""
    return evaluate_admission(path="/api/v1/gameforge/resource", method="GET", attester=attester, matrix=matrix)

def admit_gameforge_post(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit POST /api/v1/gameforge/resource."""
    return evaluate_admission(path="/api/v1/gameforge/resource", method="POST", attester=attester, matrix=matrix)

def admit_gameforge_put(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PUT /api/v1/gameforge/resource."""
    return evaluate_admission(path="/api/v1/gameforge/resource", method="PUT", attester=attester, matrix=matrix)

def admit_gameforge_patch(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PATCH /api/v1/gameforge/resource."""
    return evaluate_admission(path="/api/v1/gameforge/resource", method="PATCH", attester=attester, matrix=matrix)

def admit_gameforge_delete(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit DELETE /api/v1/gameforge/resource."""
    return evaluate_admission(path="/api/v1/gameforge/resource", method="DELETE", attester=attester, matrix=matrix)

def admit_swarm_get(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit GET /api/v1/swarm/resource."""
    return evaluate_admission(path="/api/v1/swarm/resource", method="GET", attester=attester, matrix=matrix)

def admit_swarm_post(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit POST /api/v1/swarm/resource."""
    return evaluate_admission(path="/api/v1/swarm/resource", method="POST", attester=attester, matrix=matrix)

def admit_swarm_put(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PUT /api/v1/swarm/resource."""
    return evaluate_admission(path="/api/v1/swarm/resource", method="PUT", attester=attester, matrix=matrix)

def admit_swarm_patch(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PATCH /api/v1/swarm/resource."""
    return evaluate_admission(path="/api/v1/swarm/resource", method="PATCH", attester=attester, matrix=matrix)

def admit_swarm_delete(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit DELETE /api/v1/swarm/resource."""
    return evaluate_admission(path="/api/v1/swarm/resource", method="DELETE", attester=attester, matrix=matrix)

def admit_jeeves_get(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit GET /api/v1/jeeves/resource."""
    return evaluate_admission(path="/api/v1/jeeves/resource", method="GET", attester=attester, matrix=matrix)

def admit_jeeves_post(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit POST /api/v1/jeeves/resource."""
    return evaluate_admission(path="/api/v1/jeeves/resource", method="POST", attester=attester, matrix=matrix)

def admit_jeeves_put(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PUT /api/v1/jeeves/resource."""
    return evaluate_admission(path="/api/v1/jeeves/resource", method="PUT", attester=attester, matrix=matrix)

def admit_jeeves_patch(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PATCH /api/v1/jeeves/resource."""
    return evaluate_admission(path="/api/v1/jeeves/resource", method="PATCH", attester=attester, matrix=matrix)

def admit_jeeves_delete(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit DELETE /api/v1/jeeves/resource."""
    return evaluate_admission(path="/api/v1/jeeves/resource", method="DELETE", attester=attester, matrix=matrix)

def admit_memory_get(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit GET /api/v1/memory/resource."""
    return evaluate_admission(path="/api/v1/memory/resource", method="GET", attester=attester, matrix=matrix)

def admit_memory_post(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit POST /api/v1/memory/resource."""
    return evaluate_admission(path="/api/v1/memory/resource", method="POST", attester=attester, matrix=matrix)

def admit_memory_put(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PUT /api/v1/memory/resource."""
    return evaluate_admission(path="/api/v1/memory/resource", method="PUT", attester=attester, matrix=matrix)

def admit_memory_patch(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PATCH /api/v1/memory/resource."""
    return evaluate_admission(path="/api/v1/memory/resource", method="PATCH", attester=attester, matrix=matrix)

def admit_memory_delete(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit DELETE /api/v1/memory/resource."""
    return evaluate_admission(path="/api/v1/memory/resource", method="DELETE", attester=attester, matrix=matrix)

def admit_retrieval_get(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit GET /api/v1/retrieval/resource."""
    return evaluate_admission(path="/api/v1/retrieval/resource", method="GET", attester=attester, matrix=matrix)

def admit_retrieval_post(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit POST /api/v1/retrieval/resource."""
    return evaluate_admission(path="/api/v1/retrieval/resource", method="POST", attester=attester, matrix=matrix)

def admit_retrieval_put(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PUT /api/v1/retrieval/resource."""
    return evaluate_admission(path="/api/v1/retrieval/resource", method="PUT", attester=attester, matrix=matrix)

def admit_retrieval_patch(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PATCH /api/v1/retrieval/resource."""
    return evaluate_admission(path="/api/v1/retrieval/resource", method="PATCH", attester=attester, matrix=matrix)

def admit_retrieval_delete(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit DELETE /api/v1/retrieval/resource."""
    return evaluate_admission(path="/api/v1/retrieval/resource", method="DELETE", attester=attester, matrix=matrix)

def admit_pipeline_get(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit GET /api/v1/pipeline/resource."""
    return evaluate_admission(path="/api/v1/pipeline/resource", method="GET", attester=attester, matrix=matrix)

def admit_pipeline_post(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit POST /api/v1/pipeline/resource."""
    return evaluate_admission(path="/api/v1/pipeline/resource", method="POST", attester=attester, matrix=matrix)

def admit_pipeline_put(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PUT /api/v1/pipeline/resource."""
    return evaluate_admission(path="/api/v1/pipeline/resource", method="PUT", attester=attester, matrix=matrix)

def admit_pipeline_patch(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PATCH /api/v1/pipeline/resource."""
    return evaluate_admission(path="/api/v1/pipeline/resource", method="PATCH", attester=attester, matrix=matrix)

def admit_pipeline_delete(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit DELETE /api/v1/pipeline/resource."""
    return evaluate_admission(path="/api/v1/pipeline/resource", method="DELETE", attester=attester, matrix=matrix)

def admit_intelligence_get(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit GET /api/v1/intelligence/resource."""
    return evaluate_admission(path="/api/v1/intelligence/resource", method="GET", attester=attester, matrix=matrix)

def admit_intelligence_post(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit POST /api/v1/intelligence/resource."""
    return evaluate_admission(path="/api/v1/intelligence/resource", method="POST", attester=attester, matrix=matrix)

def admit_intelligence_put(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PUT /api/v1/intelligence/resource."""
    return evaluate_admission(path="/api/v1/intelligence/resource", method="PUT", attester=attester, matrix=matrix)

def admit_intelligence_patch(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PATCH /api/v1/intelligence/resource."""
    return evaluate_admission(path="/api/v1/intelligence/resource", method="PATCH", attester=attester, matrix=matrix)

def admit_intelligence_delete(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit DELETE /api/v1/intelligence/resource."""
    return evaluate_admission(path="/api/v1/intelligence/resource", method="DELETE", attester=attester, matrix=matrix)

def admit_resilience_get(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit GET /api/v1/resilience/resource."""
    return evaluate_admission(path="/api/v1/resilience/resource", method="GET", attester=attester, matrix=matrix)

def admit_resilience_post(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit POST /api/v1/resilience/resource."""
    return evaluate_admission(path="/api/v1/resilience/resource", method="POST", attester=attester, matrix=matrix)

def admit_resilience_put(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PUT /api/v1/resilience/resource."""
    return evaluate_admission(path="/api/v1/resilience/resource", method="PUT", attester=attester, matrix=matrix)

def admit_resilience_patch(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PATCH /api/v1/resilience/resource."""
    return evaluate_admission(path="/api/v1/resilience/resource", method="PATCH", attester=attester, matrix=matrix)

def admit_resilience_delete(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit DELETE /api/v1/resilience/resource."""
    return evaluate_admission(path="/api/v1/resilience/resource", method="DELETE", attester=attester, matrix=matrix)

def admit_context_get(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit GET /api/v1/context/resource."""
    return evaluate_admission(path="/api/v1/context/resource", method="GET", attester=attester, matrix=matrix)

def admit_context_post(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit POST /api/v1/context/resource."""
    return evaluate_admission(path="/api/v1/context/resource", method="POST", attester=attester, matrix=matrix)

def admit_context_put(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PUT /api/v1/context/resource."""
    return evaluate_admission(path="/api/v1/context/resource", method="PUT", attester=attester, matrix=matrix)

def admit_context_patch(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PATCH /api/v1/context/resource."""
    return evaluate_admission(path="/api/v1/context/resource", method="PATCH", attester=attester, matrix=matrix)

def admit_context_delete(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit DELETE /api/v1/context/resource."""
    return evaluate_admission(path="/api/v1/context/resource", method="DELETE", attester=attester, matrix=matrix)

def admit_ledger_get(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit GET /api/v1/ledger/resource."""
    return evaluate_admission(path="/api/v1/ledger/resource", method="GET", attester=attester, matrix=matrix)

def admit_ledger_post(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit POST /api/v1/ledger/resource."""
    return evaluate_admission(path="/api/v1/ledger/resource", method="POST", attester=attester, matrix=matrix)

def admit_ledger_put(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PUT /api/v1/ledger/resource."""
    return evaluate_admission(path="/api/v1/ledger/resource", method="PUT", attester=attester, matrix=matrix)

def admit_ledger_patch(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PATCH /api/v1/ledger/resource."""
    return evaluate_admission(path="/api/v1/ledger/resource", method="PATCH", attester=attester, matrix=matrix)

def admit_ledger_delete(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit DELETE /api/v1/ledger/resource."""
    return evaluate_admission(path="/api/v1/ledger/resource", method="DELETE", attester=attester, matrix=matrix)

def admit_scheduler_get(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit GET /api/v1/scheduler/resource."""
    return evaluate_admission(path="/api/v1/scheduler/resource", method="GET", attester=attester, matrix=matrix)

def admit_scheduler_post(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit POST /api/v1/scheduler/resource."""
    return evaluate_admission(path="/api/v1/scheduler/resource", method="POST", attester=attester, matrix=matrix)

def admit_scheduler_put(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PUT /api/v1/scheduler/resource."""
    return evaluate_admission(path="/api/v1/scheduler/resource", method="PUT", attester=attester, matrix=matrix)

def admit_scheduler_patch(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PATCH /api/v1/scheduler/resource."""
    return evaluate_admission(path="/api/v1/scheduler/resource", method="PATCH", attester=attester, matrix=matrix)

def admit_scheduler_delete(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit DELETE /api/v1/scheduler/resource."""
    return evaluate_admission(path="/api/v1/scheduler/resource", method="DELETE", attester=attester, matrix=matrix)

def admit_genesis_get(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit GET /api/v1/genesis/resource."""
    return evaluate_admission(path="/api/v1/genesis/resource", method="GET", attester=attester, matrix=matrix)

def admit_genesis_post(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit POST /api/v1/genesis/resource."""
    return evaluate_admission(path="/api/v1/genesis/resource", method="POST", attester=attester, matrix=matrix)

def admit_genesis_put(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PUT /api/v1/genesis/resource."""
    return evaluate_admission(path="/api/v1/genesis/resource", method="PUT", attester=attester, matrix=matrix)

def admit_genesis_patch(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PATCH /api/v1/genesis/resource."""
    return evaluate_admission(path="/api/v1/genesis/resource", method="PATCH", attester=attester, matrix=matrix)

def admit_genesis_delete(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit DELETE /api/v1/genesis/resource."""
    return evaluate_admission(path="/api/v1/genesis/resource", method="DELETE", attester=attester, matrix=matrix)

def admit_capabilities_get(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit GET /api/v1/capabilities/resource."""
    return evaluate_admission(path="/api/v1/capabilities/resource", method="GET", attester=attester, matrix=matrix)

def admit_capabilities_post(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit POST /api/v1/capabilities/resource."""
    return evaluate_admission(path="/api/v1/capabilities/resource", method="POST", attester=attester, matrix=matrix)

def admit_capabilities_put(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PUT /api/v1/capabilities/resource."""
    return evaluate_admission(path="/api/v1/capabilities/resource", method="PUT", attester=attester, matrix=matrix)

def admit_capabilities_patch(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PATCH /api/v1/capabilities/resource."""
    return evaluate_admission(path="/api/v1/capabilities/resource", method="PATCH", attester=attester, matrix=matrix)

def admit_capabilities_delete(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit DELETE /api/v1/capabilities/resource."""
    return evaluate_admission(path="/api/v1/capabilities/resource", method="DELETE", attester=attester, matrix=matrix)

def admit_interface_get(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit GET /api/v1/interface/resource."""
    return evaluate_admission(path="/api/v1/interface/resource", method="GET", attester=attester, matrix=matrix)

def admit_interface_post(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit POST /api/v1/interface/resource."""
    return evaluate_admission(path="/api/v1/interface/resource", method="POST", attester=attester, matrix=matrix)

def admit_interface_put(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PUT /api/v1/interface/resource."""
    return evaluate_admission(path="/api/v1/interface/resource", method="PUT", attester=attester, matrix=matrix)

def admit_interface_patch(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PATCH /api/v1/interface/resource."""
    return evaluate_admission(path="/api/v1/interface/resource", method="PATCH", attester=attester, matrix=matrix)

def admit_interface_delete(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit DELETE /api/v1/interface/resource."""
    return evaluate_admission(path="/api/v1/interface/resource", method="DELETE", attester=attester, matrix=matrix)

def admit_auth_get(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit GET /api/v1/auth/resource."""
    return evaluate_admission(path="/api/v1/auth/resource", method="GET", attester=attester, matrix=matrix)

def admit_auth_post(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit POST /api/v1/auth/resource."""
    return evaluate_admission(path="/api/v1/auth/resource", method="POST", attester=attester, matrix=matrix)

def admit_auth_put(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PUT /api/v1/auth/resource."""
    return evaluate_admission(path="/api/v1/auth/resource", method="PUT", attester=attester, matrix=matrix)

def admit_auth_patch(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PATCH /api/v1/auth/resource."""
    return evaluate_admission(path="/api/v1/auth/resource", method="PATCH", attester=attester, matrix=matrix)

def admit_auth_delete(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit DELETE /api/v1/auth/resource."""
    return evaluate_admission(path="/api/v1/auth/resource", method="DELETE", attester=attester, matrix=matrix)

def admit_cognition_get(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit GET /api/v1/cognition/resource."""
    return evaluate_admission(path="/api/v1/cognition/resource", method="GET", attester=attester, matrix=matrix)

def admit_cognition_post(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit POST /api/v1/cognition/resource."""
    return evaluate_admission(path="/api/v1/cognition/resource", method="POST", attester=attester, matrix=matrix)

def admit_cognition_put(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PUT /api/v1/cognition/resource."""
    return evaluate_admission(path="/api/v1/cognition/resource", method="PUT", attester=attester, matrix=matrix)

def admit_cognition_patch(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PATCH /api/v1/cognition/resource."""
    return evaluate_admission(path="/api/v1/cognition/resource", method="PATCH", attester=attester, matrix=matrix)

def admit_cognition_delete(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit DELETE /api/v1/cognition/resource."""
    return evaluate_admission(path="/api/v1/cognition/resource", method="DELETE", attester=attester, matrix=matrix)

def admit_fabric_get(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit GET /api/v1/fabric/resource."""
    return evaluate_admission(path="/api/v1/fabric/resource", method="GET", attester=attester, matrix=matrix)

def admit_fabric_post(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit POST /api/v1/fabric/resource."""
    return evaluate_admission(path="/api/v1/fabric/resource", method="POST", attester=attester, matrix=matrix)

def admit_fabric_put(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PUT /api/v1/fabric/resource."""
    return evaluate_admission(path="/api/v1/fabric/resource", method="PUT", attester=attester, matrix=matrix)

def admit_fabric_patch(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PATCH /api/v1/fabric/resource."""
    return evaluate_admission(path="/api/v1/fabric/resource", method="PATCH", attester=attester, matrix=matrix)

def admit_fabric_delete(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit DELETE /api/v1/fabric/resource."""
    return evaluate_admission(path="/api/v1/fabric/resource", method="DELETE", attester=attester, matrix=matrix)

def admit_legions_get(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit GET /api/v1/legions/resource."""
    return evaluate_admission(path="/api/v1/legions/resource", method="GET", attester=attester, matrix=matrix)

def admit_legions_post(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit POST /api/v1/legions/resource."""
    return evaluate_admission(path="/api/v1/legions/resource", method="POST", attester=attester, matrix=matrix)

def admit_legions_put(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PUT /api/v1/legions/resource."""
    return evaluate_admission(path="/api/v1/legions/resource", method="PUT", attester=attester, matrix=matrix)

def admit_legions_patch(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PATCH /api/v1/legions/resource."""
    return evaluate_admission(path="/api/v1/legions/resource", method="PATCH", attester=attester, matrix=matrix)

def admit_legions_delete(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit DELETE /api/v1/legions/resource."""
    return evaluate_admission(path="/api/v1/legions/resource", method="DELETE", attester=attester, matrix=matrix)

def admit_governance_get(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit GET /api/v1/governance/resource."""
    return evaluate_admission(path="/api/v1/governance/resource", method="GET", attester=attester, matrix=matrix)

def admit_governance_post(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit POST /api/v1/governance/resource."""
    return evaluate_admission(path="/api/v1/governance/resource", method="POST", attester=attester, matrix=matrix)

def admit_governance_put(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PUT /api/v1/governance/resource."""
    return evaluate_admission(path="/api/v1/governance/resource", method="PUT", attester=attester, matrix=matrix)

def admit_governance_patch(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PATCH /api/v1/governance/resource."""
    return evaluate_admission(path="/api/v1/governance/resource", method="PATCH", attester=attester, matrix=matrix)

def admit_governance_delete(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit DELETE /api/v1/governance/resource."""
    return evaluate_admission(path="/api/v1/governance/resource", method="DELETE", attester=attester, matrix=matrix)

def admit_lafs_get(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit GET /api/v1/lafs/resource."""
    return evaluate_admission(path="/api/v1/lafs/resource", method="GET", attester=attester, matrix=matrix)

def admit_lafs_post(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit POST /api/v1/lafs/resource."""
    return evaluate_admission(path="/api/v1/lafs/resource", method="POST", attester=attester, matrix=matrix)

def admit_lafs_put(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PUT /api/v1/lafs/resource."""
    return evaluate_admission(path="/api/v1/lafs/resource", method="PUT", attester=attester, matrix=matrix)

def admit_lafs_patch(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PATCH /api/v1/lafs/resource."""
    return evaluate_admission(path="/api/v1/lafs/resource", method="PATCH", attester=attester, matrix=matrix)

def admit_lafs_delete(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit DELETE /api/v1/lafs/resource."""
    return evaluate_admission(path="/api/v1/lafs/resource", method="DELETE", attester=attester, matrix=matrix)

def admit_studio_get(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit GET /api/v1/studio/resource."""
    return evaluate_admission(path="/api/v1/studio/resource", method="GET", attester=attester, matrix=matrix)

def admit_studio_post(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit POST /api/v1/studio/resource."""
    return evaluate_admission(path="/api/v1/studio/resource", method="POST", attester=attester, matrix=matrix)

def admit_studio_put(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PUT /api/v1/studio/resource."""
    return evaluate_admission(path="/api/v1/studio/resource", method="PUT", attester=attester, matrix=matrix)

def admit_studio_patch(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PATCH /api/v1/studio/resource."""
    return evaluate_admission(path="/api/v1/studio/resource", method="PATCH", attester=attester, matrix=matrix)

def admit_studio_delete(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit DELETE /api/v1/studio/resource."""
    return evaluate_admission(path="/api/v1/studio/resource", method="DELETE", attester=attester, matrix=matrix)

def admit_court_get(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit GET /api/v1/court/resource."""
    return evaluate_admission(path="/api/v1/court/resource", method="GET", attester=attester, matrix=matrix)

def admit_court_post(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit POST /api/v1/court/resource."""
    return evaluate_admission(path="/api/v1/court/resource", method="POST", attester=attester, matrix=matrix)

def admit_court_put(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PUT /api/v1/court/resource."""
    return evaluate_admission(path="/api/v1/court/resource", method="PUT", attester=attester, matrix=matrix)

def admit_court_patch(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PATCH /api/v1/court/resource."""
    return evaluate_admission(path="/api/v1/court/resource", method="PATCH", attester=attester, matrix=matrix)

def admit_court_delete(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit DELETE /api/v1/court/resource."""
    return evaluate_admission(path="/api/v1/court/resource", method="DELETE", attester=attester, matrix=matrix)

def admit_treasury_get(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit GET /api/v1/treasury/resource."""
    return evaluate_admission(path="/api/v1/treasury/resource", method="GET", attester=attester, matrix=matrix)

def admit_treasury_post(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit POST /api/v1/treasury/resource."""
    return evaluate_admission(path="/api/v1/treasury/resource", method="POST", attester=attester, matrix=matrix)

def admit_treasury_put(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PUT /api/v1/treasury/resource."""
    return evaluate_admission(path="/api/v1/treasury/resource", method="PUT", attester=attester, matrix=matrix)

def admit_treasury_patch(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PATCH /api/v1/treasury/resource."""
    return evaluate_admission(path="/api/v1/treasury/resource", method="PATCH", attester=attester, matrix=matrix)

def admit_treasury_delete(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit DELETE /api/v1/treasury/resource."""
    return evaluate_admission(path="/api/v1/treasury/resource", method="DELETE", attester=attester, matrix=matrix)

def admit_reputation_get(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit GET /api/v1/reputation/resource."""
    return evaluate_admission(path="/api/v1/reputation/resource", method="GET", attester=attester, matrix=matrix)

def admit_reputation_post(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit POST /api/v1/reputation/resource."""
    return evaluate_admission(path="/api/v1/reputation/resource", method="POST", attester=attester, matrix=matrix)

def admit_reputation_put(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PUT /api/v1/reputation/resource."""
    return evaluate_admission(path="/api/v1/reputation/resource", method="PUT", attester=attester, matrix=matrix)

def admit_reputation_patch(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PATCH /api/v1/reputation/resource."""
    return evaluate_admission(path="/api/v1/reputation/resource", method="PATCH", attester=attester, matrix=matrix)

def admit_reputation_delete(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit DELETE /api/v1/reputation/resource."""
    return evaluate_admission(path="/api/v1/reputation/resource", method="DELETE", attester=attester, matrix=matrix)

def admit_diet_get(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit GET /api/v1/diet/resource."""
    return evaluate_admission(path="/api/v1/diet/resource", method="GET", attester=attester, matrix=matrix)

def admit_diet_post(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit POST /api/v1/diet/resource."""
    return evaluate_admission(path="/api/v1/diet/resource", method="POST", attester=attester, matrix=matrix)

def admit_diet_put(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PUT /api/v1/diet/resource."""
    return evaluate_admission(path="/api/v1/diet/resource", method="PUT", attester=attester, matrix=matrix)

def admit_diet_patch(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PATCH /api/v1/diet/resource."""
    return evaluate_admission(path="/api/v1/diet/resource", method="PATCH", attester=attester, matrix=matrix)

def admit_diet_delete(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit DELETE /api/v1/diet/resource."""
    return evaluate_admission(path="/api/v1/diet/resource", method="DELETE", attester=attester, matrix=matrix)

def admit_boardroom_get(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit GET /api/v1/boardroom/resource."""
    return evaluate_admission(path="/api/v1/boardroom/resource", method="GET", attester=attester, matrix=matrix)

def admit_boardroom_post(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit POST /api/v1/boardroom/resource."""
    return evaluate_admission(path="/api/v1/boardroom/resource", method="POST", attester=attester, matrix=matrix)

def admit_boardroom_put(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PUT /api/v1/boardroom/resource."""
    return evaluate_admission(path="/api/v1/boardroom/resource", method="PUT", attester=attester, matrix=matrix)

def admit_boardroom_patch(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit PATCH /api/v1/boardroom/resource."""
    return evaluate_admission(path="/api/v1/boardroom/resource", method="PATCH", attester=attester, matrix=matrix)

def admit_boardroom_delete(attester: Optional[str] = "gate-bot", *, matrix: Optional[AdmissionMatrix] = None) -> AdmissionDecision:
    """Admit DELETE /api/v1/boardroom/resource."""
    return evaluate_admission(path="/api/v1/boardroom/resource", method="DELETE", attester=attester, matrix=matrix)


def batch_admit(cases: Sequence[Tuple[str, str, Optional[str]]], *, matrix: Optional[AdmissionMatrix] = None) -> List[AdmissionDecision]:
    return [evaluate_admission(path=p, method=m, attester=a, matrix=matrix) for (p, m, a) in cases]


def summarize_outcomes(decisions: Iterable[AdmissionDecision]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for d in decisions:
        counts[d.outcome.value] = counts.get(d.outcome.value, 0) + 1
    return counts
