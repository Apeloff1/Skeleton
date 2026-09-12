"""High-integrity helpers for capturing and closing Jeeves runtime sessions."""
from __future__ import annotations

from typing import TYPE_CHECKING

from skeleton.school.runtime_replay import RuntimeReplaySnapshot
from skeleton.school.session_runtime import SessionPhase, SessionTransition

if TYPE_CHECKING:
    from skeleton.school.session_runtime import JeevesSessionRuntime


def capture_runtime(runtime: "JeevesSessionRuntime") -> RuntimeReplaySnapshot:
    """Capture a runtime using its intrinsic, lifecycle-bound provenance."""
    return RuntimeReplaySnapshot.capture(
        session_id=runtime.session_id,
        phase=runtime.phase,
        events=runtime.events,
        selected_policy=runtime._selected_policy,
        rejected_policies=tuple(
            record.action
            for record in runtime.ledger.session(runtime.session_id)
            if record.disposition.value == "rejected"
        ),
        ledger=runtime.ledger,
        pipeline_contract_digest=runtime.pipeline_contract_digest,
        provenance_digest=runtime.provenance_digest,
    )


def complete_runtime(runtime: "JeevesSessionRuntime", *, rationale: str = "complete Jeeves session") -> SessionTransition:
    """Close a runtime through its normal state machine and emit a terminal event."""
    if runtime.phase is SessionPhase.COMPLETE:
        raise ValueError("session is already complete")
    if runtime.phase is SessionPhase.COMMIT:
        return runtime.transition(SessionPhase.COMPLETE, rationale=rationale)
    if runtime.phase is SessionPhase.SCHEDULE:
        return runtime.transition(SessionPhase.COMPLETE, rationale=rationale)
    raise ValueError(f"session must be in commit or schedule before completion, got {runtime.phase.value}")
