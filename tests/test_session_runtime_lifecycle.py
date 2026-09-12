import pytest

from skeleton.school.curriculum import CurriculumGraph
from skeleton.school.jeeves import JeevesControlPlane
from skeleton.school.session_runtime import JeevesSessionRuntime, SessionPhase


def _runtime() -> JeevesSessionRuntime:
    curriculum = CurriculumGraph()
    return JeevesSessionRuntime(JeevesControlPlane(curriculum), curriculum)


def test_runtime_rejects_overlapping_session_start():
    runtime = _runtime()
    runtime._prepare_session("first")

    with pytest.raises(RuntimeError, match="still active"):
        runtime._prepare_session("second")


def test_runtime_resets_ephemeral_state_after_completed_session():
    runtime = _runtime()
    runtime._prepare_session("first")
    runtime.phase = SessionPhase.COMPLETE
    runtime._sequence = 17
    runtime._last_decision_id = "first:decision"
    runtime._selected_policy = "practice"
    runtime._prepare_session("second")

    assert runtime.session_id == "second"
    assert runtime.phase is SessionPhase.INTAKE
    assert runtime.events == []
    assert runtime._sequence == 0
    assert runtime._last_decision_id is None
    assert runtime._selected_policy is None


def test_runtime_rejects_reusing_a_ledger_session_id():
    runtime = _runtime()
    runtime._prepare_session("first")
    runtime._record_decision(
        decision_id="first:root",
        action="practice",
        rationale=("root",),
        state={},
        policy={},
    )
    runtime.phase = SessionPhase.COMPLETE

    with pytest.raises(ValueError, match="already exists"):
        runtime._prepare_session("first")
