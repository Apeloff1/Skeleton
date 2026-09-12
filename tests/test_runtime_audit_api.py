from skeleton.school.curriculum import CurriculumGraph
from skeleton.school.jeeves import JeevesControlPlane
from skeleton.school.runtime_audit_api import capture_runtime, complete_runtime
from skeleton.school.runtime_replay import audit_runtime
from skeleton.school.student import StudentProfile


def _runtime():
    graph = CurriculumGraph()
    return __import__("skeleton.school.session_runtime", fromlist=["JeevesSessionRuntime"]).JeevesSessionRuntime(
        control=JeevesControlPlane(graph), curriculum=graph
    )


def test_capture_runtime_is_deterministic_and_binds_ledger():
    runtime = _runtime()
    student = StudentProfile(student_id="s1", name="Test")
    runtime.begin(student, session_id="capture-1", query_terms=("python",))
    first = capture_runtime(runtime)
    second = capture_runtime(runtime)
    assert first == second
    assert first.session_id == "capture-1"
    assert first.ledger_count == len(runtime.ledger.records)
    assert audit_runtime(first, runtime.ledger).valid


def test_complete_runtime_requires_terminal_ready_phase_and_audits_complete():
    runtime = _runtime()
    student = StudentProfile(student_id="s2", name="Test")
    runtime.begin(student, session_id="complete-1", query_terms=("python",))
    try:
        complete_runtime(runtime)
    except ValueError as exc:
        assert "commit or schedule" in str(exc)
    else:
        raise AssertionError("completion should require a terminal-ready phase")

    runtime.phase = runtime.phase.COMMIT
    complete_runtime(runtime)
    snapshot = capture_runtime(runtime)
    audit = audit_runtime(snapshot, runtime.ledger)
    assert runtime.phase.value == "complete"
    assert audit.valid
    assert snapshot.events[-1][1] == "complete"
