from __future__ import annotations

import json
from pathlib import Path

from scripts.check_autonomous_run_state import (
    ACTIONS_RUN_CLASSES,
    CONFLICT_DOMAIN,
    DOCUMENT_FIELDS,
    INITIAL_STATE,
    LEGAL_TRANSITIONS,
    SCHEMA_VERSION,
    STATES,
    STATE_SET,
    TASK_ID,
    TERMINAL_STATES,
    TRANSITION_FIELDS,
    is_legal_transition,
    main,
    validate_autonomous_run,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / "scripts" / "check_autonomous_run_state.py"


def _doc(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": "autonomous-run-s451-001",
        "state": "scheduled",
        "history": [],
        "evidence_refs": ["ops.spec.autonomous_run_state:s451"],
    }
    payload.update(overrides)
    return payload


def _happy_path() -> dict[str, object]:
    return _doc(
        state="published",
        history=[
            {"from": "scheduled", "to": "queued"},
            {"from": "queued", "to": "running"},
            {"from": "running", "to": "validated"},
            {"from": "validated", "to": "published"},
        ],
    )


def test_closed_state_set_and_identity() -> None:
    assert TASK_ID == "reserve-S451-autonomous-run-state"
    assert CONFLICT_DOMAIN == "ops.spec.autonomous_run_state"
    assert SCHEMA_VERSION == 1
    assert STATES == (
        "scheduled",
        "queued",
        "running",
        "blocked",
        "failed-closed",
        "validated",
        "published",
        "no-op",
    )
    assert len(STATES) == len(STATE_SET) == 8
    assert INITIAL_STATE == "scheduled"
    assert TERMINAL_STATES == {"failed-closed", "published", "no-op"}
    assert DOCUMENT_FIELDS == {
        "schema_version",
        "run_id",
        "state",
        "history",
        "evidence_refs",
    }
    assert TRANSITION_FIELDS == {"from", "to"}
    source = CHECKER.read_text(encoding="utf-8")
    assert "TASK_ID" in source
    assert "TASK_KEY" not in source
    errors = validate_autonomous_run(["not", "an", "object"])
    assert errors and errors[0].startswith("autonomous-run-state ")


def test_valid_scheduled_run_has_no_violations() -> None:
    assert validate_autonomous_run(_doc()) == []


def test_valid_happy_path_to_published() -> None:
    assert validate_autonomous_run(_happy_path()) == []
    assert is_legal_transition("scheduled", "queued")
    assert is_legal_transition("queued", "running")
    assert is_legal_transition("running", "validated")
    assert is_legal_transition("validated", "published")


def test_valid_blocked_resume_and_failed_closed() -> None:
    blocked = _doc(
        state="running",
        history=[
            {"from": "scheduled", "to": "blocked"},
            {"from": "blocked", "to": "queued"},
            {"from": "queued", "to": "running"},
        ],
    )
    assert validate_autonomous_run(blocked) == []
    failed = _doc(
        state="failed-closed",
        history=[
            {"from": "scheduled", "to": "queued"},
            {"from": "queued", "to": "running"},
            {"from": "running", "to": "failed-closed"},
        ],
    )
    assert validate_autonomous_run(failed) == []
    noop = _doc(
        state="no-op",
        history=[{"from": "scheduled", "to": "no-op"}],
    )
    assert validate_autonomous_run(noop) == []


def test_unknown_state_fails_closed() -> None:
    errors = validate_autonomous_run(_doc(state="mystery"))
    assert any("autonomous-run-state unknown state" in item for item in errors)
    assert any("mystery" in item for item in errors)
    history_unknown = validate_autonomous_run(
        _doc(
            state="queued",
            history=[{"from": "scheduled", "to": "in_progress"}],
        )
    )
    assert any("autonomous-run-state unknown state" in item for item in history_unknown)
    assert any("in_progress" in item for item in history_unknown)
    underscore = validate_autonomous_run(_doc(state="failed_closed"))
    assert any("autonomous-run-state unknown state" in item for item in underscore)


def test_unknown_fields_fail_closed() -> None:
    errors = validate_autonomous_run(_doc(owner="night", status="queued"))
    assert any("autonomous-run-state unknown field" in item for item in errors)
    assert any("owner" in item for item in errors)
    assert any("status" in item for item in errors)


def test_unknown_transition_fields_fail_closed() -> None:
    errors = validate_autonomous_run(
        _doc(
            state="queued",
            history=[{"from": "scheduled", "to": "queued", "reason": "admitted", "at": "now"}],
        )
    )
    assert any("autonomous-run-state unknown field" in item for item in errors)
    assert any("reason" in item for item in errors)
    assert any("at" in item for item in errors)


def test_illegal_skip_ahead_transitions_fail_closed() -> None:
    skip_queue = validate_autonomous_run(
        _doc(
            state="running",
            history=[{"from": "scheduled", "to": "running"}],
        )
    )
    assert any("autonomous-run-state illegal transition" in item for item in skip_queue)
    assert not is_legal_transition("scheduled", "running")
    skip_validate = validate_autonomous_run(
        _doc(
            state="published",
            history=[
                {"from": "scheduled", "to": "queued"},
                {"from": "queued", "to": "running"},
                {"from": "running", "to": "published"},
            ],
        )
    )
    assert any("autonomous-run-state illegal transition" in item for item in skip_validate)
    assert not is_legal_transition("running", "published")
    assert not is_legal_transition("queued", "validated")
    assert not is_legal_transition("blocked", "published")
    assert not is_legal_transition("scheduled", "validated")


def test_terminal_states_cannot_transition() -> None:
    for terminal in sorted(TERMINAL_STATES):
        for target in STATES:
            assert not is_legal_transition(terminal, target)
    published_again = validate_autonomous_run(
        _doc(
            state="queued",
            history=[
                {"from": "scheduled", "to": "queued"},
                {"from": "queued", "to": "running"},
                {"from": "running", "to": "validated"},
                {"from": "validated", "to": "published"},
                {"from": "published", "to": "queued"},
            ],
        )
    )
    assert any("autonomous-run-state illegal transition" in item for item in published_again)
    assert any("terminal state published" in item for item in published_again)
    failed_retry = validate_autonomous_run(
        _doc(
            state="running",
            history=[
                {"from": "scheduled", "to": "failed-closed"},
                {"from": "failed-closed", "to": "running"},
            ],
        )
    )
    assert any("terminal state failed-closed" in item for item in failed_retry)
    noop_retry = validate_autonomous_run(
        _doc(
            state="queued",
            history=[
                {"from": "scheduled", "to": "no-op"},
                {"from": "no-op", "to": "queued"},
            ],
        )
    )
    assert any("terminal state no-op" in item for item in noop_retry)


def test_history_must_chain_and_match_state() -> None:
    broken_chain = validate_autonomous_run(
        _doc(
            state="running",
            history=[
                {"from": "scheduled", "to": "queued"},
                {"from": "blocked", "to": "running"},
            ],
        )
    )
    assert any("autonomous-run-state illegal transition" in item for item in broken_chain)
    assert any("does not continue" in item for item in broken_chain)
    mismatched = validate_autonomous_run(
        _doc(
            state="blocked",
            history=[{"from": "scheduled", "to": "queued"}],
        )
    )
    assert any("does not match history[-1].to" in item for item in mismatched)
    not_from_scheduled = validate_autonomous_run(
        _doc(
            state="running",
            history=[{"from": "queued", "to": "running"}],
        )
    )
    assert any("history[0].from must be scheduled" in item for item in not_from_scheduled)


def test_empty_history_only_for_scheduled() -> None:
    errors = validate_autonomous_run(_doc(state="queued", history=[]))
    assert any("autonomous-run-state illegal transition" in item for item in errors)
    assert any("empty history is only valid" in item for item in errors)
    assert validate_autonomous_run(_doc(state="scheduled", history=[])) == []


def test_missing_fields_fail_closed() -> None:
    document = _doc()
    del document["run_id"]
    del document["evidence_refs"]
    errors = validate_autonomous_run(document)
    assert any("autonomous-run-state missing_value field" in item for item in errors)
    assert any("run_id" in item for item in errors)
    assert any("autonomous-run-state missing_value evidence_refs" in item for item in errors)
    transition = validate_autonomous_run(
        _doc(state="queued", history=[{"from": "scheduled"}])
    )
    assert any("autonomous-run-state missing_value field" in item for item in transition)
    assert any("to" in item for item in transition)


def test_wrong_types_and_blank_values_fail_closed() -> None:
    errors = validate_autonomous_run(
        _doc(
            schema_version=True,
            run_id="  ",
            history="scheduled",
            evidence_refs="",
        )
    )
    assert any("autonomous-run-state unknown schema_version" in item for item in errors)
    assert any("autonomous-run-state missing_value run_id" in item for item in errors)
    assert any("autonomous-run-state unknown history_type" in item for item in errors)
    assert any("autonomous-run-state missing_value evidence_refs" in item for item in errors)
    not_object = validate_autonomous_run(
        _doc(state="queued", history=[["scheduled", "queued"]])
    )
    assert any("autonomous-run-state unknown transition_type" in item for item in not_object)
    blank_refs = validate_autonomous_run(_doc(evidence_refs=["", "  "]))
    assert any("autonomous-run-state unknown evidence_ref" in item for item in blank_refs)


def test_wrong_schema_version_fails_closed() -> None:
    errors = validate_autonomous_run(_doc(schema_version=2))
    assert any("autonomous-run-state unknown schema_version" in item for item in errors)


def test_non_object_root_fails_closed() -> None:
    errors = validate_autonomous_run(["not", "an", "object"])
    assert errors == [
        "autonomous-run-state unknown root_type: autonomous-run document must be an object"
    ]


def test_self_transitions_are_illegal() -> None:
    for state in STATES:
        assert not is_legal_transition(state, state)
    errors = validate_autonomous_run(
        _doc(
            state="queued",
            history=[
                {"from": "scheduled", "to": "queued"},
                {"from": "queued", "to": "queued"},
            ],
        )
    )
    assert any("autonomous-run-state illegal transition" in item for item in errors)
    assert ("queued", "queued") not in LEGAL_TRANSITIONS


def test_cli_accepts_valid_fixture(tmp_path: Path, capsys) -> None:
    path = tmp_path / "autonomous-run.json"
    path.write_text(json.dumps(_happy_path()), encoding="utf-8")
    assert main([str(path)]) == 0
    assert "Autonomous-run state schema v1 accepted" in capsys.readouterr().out


def test_cli_rejects_invalid_document(tmp_path: Path, capsys) -> None:
    path = tmp_path / "autonomous-run.json"
    path.write_text(
        json.dumps(_doc(state="running", extra=True, history=[{"from": "scheduled", "to": "running"}])),
        encoding="utf-8",
    )
    assert main([str(path)]) == 1
    stderr = capsys.readouterr().err
    assert "Autonomous-run state schema validation failed:" in stderr
    assert "autonomous-run-state unknown field" in stderr
    assert "autonomous-run-state illegal transition" in stderr


def test_cli_rejects_unreadable_json(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not-json", encoding="utf-8")
    try:
        main([str(path)])
    except SystemExit as exc:
        assert "autonomous-run-state unreadable json" in str(exc)
    else:
        raise AssertionError("unreadable JSON must fail closed")


def test_cli_rejects_missing_document(tmp_path: Path) -> None:
    path = tmp_path / "missing.json"
    try:
        main([str(path)])
    except SystemExit as exc:
        assert "autonomous-run-state unreadable missing_doc" in str(exc)
    else:
        raise AssertionError("missing document must fail closed")


def test_distinct_from_actions_run_state_classification() -> None:
    assert STATE_SET.isdisjoint(ACTIONS_RUN_CLASSES)
    assert "retryable" not in STATE_SET
    assert "authoritative_failure" not in STATE_SET
    assert TASK_ID != "reserve-S002-run-state-classification"
    assert CONFLICT_DOMAIN != "ci.readonly.run_classification"
    source = CHECKER.read_text(encoding="utf-8")
    assert "autonomous-run lifecycle" in source
    assert "GitHub Actions" in source
    assert "conclusion" not in source
    assert "head_sha" not in source
    assert "replaced_by" not in source
    for klass in ("retryable", "stale", "superseded", "authoritative_failure"):
        errors = validate_autonomous_run(_doc(state=klass))
        assert any("autonomous-run-state unknown state" in item for item in errors)


def test_not_wired_into_quality_gates() -> None:
    quality_gates = (REPO_ROOT / "scripts" / "quality-gates.sh").read_text(encoding="utf-8")
    assert "check_autonomous_run_state.py" not in quality_gates
    assert "test_autonomous_run_state.py" not in quality_gates
