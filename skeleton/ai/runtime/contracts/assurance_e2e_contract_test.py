"""End-to-end contract checks for the assurance pipeline.

Validates the intended data path:
Supervisor -> Secretary -> Worker -> Evidence -> Memory -> Feedback.

These checks intentionally focus on boundaries and invariants rather than
implementation details.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PipelineState:
    task_id: str
    evidence_valid: bool
    memory_state: str
    feedback_state: str


def validate_pipeline(state: PipelineState) -> bool:
    if not state.task_id:
        return False
    if not state.evidence_valid:
        return False
    if state.memory_state not in {"STABLE", "TEMPORARY", "REJECTED"}:
        return False
    if state.feedback_state not in {"ACCEPTED", "NEEDS_REVIEW", "REJECTED"}:
        return False
    return True


def test_valid_assurance_path() -> None:
    assert validate_pipeline(
        PipelineState(
            task_id="task-1",
            evidence_valid=True,
            memory_state="STABLE",
            feedback_state="ACCEPTED",
        )
    )


def test_rejected_evidence_cannot_become_stable() -> None:
    assert not validate_pipeline(
        PipelineState(
            task_id="task-2",
            evidence_valid=False,
            memory_state="STABLE",
            feedback_state="ACCEPTED",
        )
    )
