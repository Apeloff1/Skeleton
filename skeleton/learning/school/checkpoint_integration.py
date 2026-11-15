"""Explicit Academy control-plane checkpoint integration.

This wiring is called at a quiescent session boundary. It does not resume
in-flight decisions, auto-commit on import or change the current app startup.
"""
from __future__ import annotations

from dataclasses import dataclass

from skeleton.learning.school.checkpoint_codec import AcademyState
from skeleton.learning.school.checkpoint_store import AcademyCheckpointStore, AcademyReceipt
from skeleton.learning.school.curriculum import CurriculumGraph
from skeleton.learning.school.jeeves import JeevesControlPlane
from skeleton.learning.school.session_runtime import JeevesSessionRuntime, SessionPhase
from skeleton.learning.school.student import StudentProfile


@dataclass(frozen=True, slots=True)
class RestoredAcademy:
    student: StudentProfile
    runtime: JeevesSessionRuntime
    receipt: AcademyReceipt


def checkpoint_completed_session(store: AcademyCheckpointStore, runtime: JeevesSessionRuntime,
                                 student: StudentProfile, *, expected_revision: int,
                                 request_id: str,
                                 trusted_head: AcademyReceipt | None = None) -> AcademyReceipt:
    if type(store) is not AcademyCheckpointStore or type(runtime) is not JeevesSessionRuntime:
        raise TypeError("canonical Academy storage and runtime required")
    if runtime.phase is not SessionPhase.COMPLETE or not runtime.session_id:
        raise ValueError("checkpoint requires a completed, quiescent session")
    # Bind the actual runtime audit to the same decision ledger that will be saved.
    from skeleton.learning.school.runtime_audit_api import capture_runtime
    from skeleton.learning.school.runtime_capsule import RuntimeIntegrityCapsule
    capsule = RuntimeIntegrityCapsule.capture(capture_runtime(runtime), runtime.ledger)
    if not capsule.verify(runtime.ledger).valid:
        raise ValueError("Academy runtime audit failed")
    return store.save(
        AcademyState(student, runtime.control.memory, runtime.control.reflections,
                     runtime.control.policy_calibrator, runtime.ledger),
        expected_revision=expected_revision, request_id=request_id, trusted_head=trusted_head,
    )


def restore_academy(store: AcademyCheckpointStore, curriculum: CurriculumGraph,
                    student_id: str, *, trusted_head: AcademyReceipt | None = None) -> RestoredAcademy | None:
    revision = store.load(student_id, trusted_head=trusted_head)
    if revision is None:
        return None
    state = revision.state
    control = JeevesControlPlane(curriculum, memory=state.memory,
                                 reflections=state.reflections, policy_calibrator=state.calibrator)
    # Deliberately new session boundary. Old live event streams, knowledge graph
    # and epistemic transient state are not silently reconstructed.
    runtime = JeevesSessionRuntime(control, curriculum, ledger=state.ledger)
    return RestoredAcademy(state.student, runtime, revision.receipt)
