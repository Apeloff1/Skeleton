from __future__ import annotations

import json
from pathlib import Path

from scripts.check_run_state_classification import (
    CLASSES,
    classify_document,
    classify_run,
    main,
)


def test_closed_class_set() -> None:
    assert CLASSES == (
        "retryable",
        "stale",
        "superseded",
        "authoritative_failure",
        "complete",
        "unknown",
    )
    assert len(CLASSES) == len(set(CLASSES))


def test_queued_is_retryable() -> None:
    assert classify_run({"status": "queued", "conclusion": None}) == "retryable"
    assert classify_run({"status": "in_progress"}) == "retryable"


def test_timeout_is_retryable() -> None:
    assert classify_run({"status": "completed", "conclusion": "timed_out"}) == "retryable"


def test_cancelled_without_newer_is_retryable() -> None:
    assert classify_run({"status": "completed", "conclusion": "cancelled"}) == "retryable"
    assert classify_run({"status": "completed", "conclusion": "canceled"}) == "retryable"


def test_cancelled_with_newer_is_stale() -> None:
    assert (
        classify_run({"status": "completed", "conclusion": "cancelled", "newer_run": True})
        == "stale"
    )


def test_failure_is_authoritative() -> None:
    assert classify_run({"status": "completed", "conclusion": "failure"}) == "authoritative_failure"


def test_success_is_complete_not_unknown() -> None:
    assert classify_run({"status": "completed", "conclusion": "success"}) == "complete"


def test_head_sha_behind_current_is_superseded() -> None:
    run = {"status": "completed", "conclusion": "failure", "head_sha": "aaa"}
    assert classify_run(run, current_sha="bbb") == "superseded"
    queued = {"status": "queued", "head_sha": "old"}
    assert classify_run(queued, current_sha="new") == "superseded"


def test_replaced_by_is_superseded() -> None:
    assert classify_run({"status": "completed", "conclusion": "cancelled", "replaced_by": 9}) == "superseded"


def test_unknown_status_fails_closed() -> None:
    assert classify_run({"status": "mystery"}) == "unknown"
    assert classify_run({"status": "completed", "conclusion": "explode"}) == "unknown"
    assert classify_run(["not", "an", "object"]) == "unknown"
    assert classify_run({"status": "queued", "extra": True}) == "unknown"


def test_document_unknown_rows_are_violations() -> None:
    rows, errors = classify_document(
        {
            "schema_version": 1,
            "runs": [{"status": "completed", "conclusion": "nope"}],
        }
    )
    assert rows[0]["class"] == "unknown"
    assert any("run-state unknown unclassified" in item for item in errors)


def test_valid_document_classifies_without_violations() -> None:
    rows, errors = classify_document(
        {
            "schema_version": 1,
            "current_sha": "bbb",
            "runs": [
                {"status": "queued", "id": 1},
                {"status": "completed", "conclusion": "failure", "id": 2},
                {"status": "completed", "conclusion": "success", "id": 3},
                {"status": "completed", "conclusion": "failure", "head_sha": "aaa", "id": 4},
            ],
        }
    )
    assert errors == []
    assert [row["class"] for row in rows] == [
        "retryable",
        "authoritative_failure",
        "complete",
        "superseded",
    ]


def test_cli_accepts_valid_fixture(tmp_path: Path, capsys) -> None:
    path = tmp_path / "runs.json"
    path.write_text(
        json.dumps({"schema_version": 1, "runs": [{"status": "completed", "conclusion": "success"}]}),
        encoding="utf-8",
    )
    assert main([str(path)]) == 0
    assert "complete=1" in capsys.readouterr().out


def test_cli_rejects_unknown_runs(tmp_path: Path) -> None:
    path = tmp_path / "runs.json"
    path.write_text(
        json.dumps({"schema_version": 1, "runs": [{"status": "nope"}]}),
        encoding="utf-8",
    )
    assert main([str(path)]) == 1
