"""Fail-closed regressions for the current-PR blocker map (#969 Seed 01)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.check_pr_blocker_map import (
    BLOCKING_CONCLUSIONS,
    CLASSES,
    CONFLICT_DOMAIN,
    QUEUED_STATUSES,
    ROLLUP_PRIORITY,
    SCHEMA_VERSION,
    TASK_KEY,
    classify_check,
    classify_document,
    first_rollup,
    main,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_pr_blocker_map.py"
HEAD = "abc123def456"


def _pr(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "number": 42,
        "state": "open",
        "head_sha": HEAD,
        "owning_issue": "#969",
        "repair": None,
    }
    payload.update(overrides)
    return payload


def _check(name: str, *, status: str = "completed", conclusion: object = "success", head_sha: str = HEAD) -> dict[str, object]:
    return {
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "head_sha": head_sha,
    }


def _doc(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "task_key": TASK_KEY,
        "conflict_domain": CONFLICT_DOMAIN,
        "pull_request": _pr(),
        "required_checks": ["Merge Readiness"],
        "checks": [_check("Merge Readiness")],
    }
    payload.update(overrides)
    return payload


def test_task_identity_and_closed_class_set() -> None:
    assert TASK_KEY == "reserve-S001-current-pr-blocker-map"
    assert CONFLICT_DOMAIN == "ci.readonly.blocker_map"
    assert SCHEMA_VERSION == 1
    assert ROLLUP_PRIORITY == ("blocking", "queued", "stale", "success")
    assert CLASSES == ("blocking", "queued", "stale", "success", "unknown")
    assert len(CLASSES) == len(set(CLASSES))
    assert "retryable" not in CLASSES
    assert "complete" not in CLASSES
    assert "authoritative_failure" not in CLASSES
    assert "superseded" not in CLASSES


def test_script_is_stdlib_and_has_no_github_mutation() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    forbidden = (
        "import urllib",
        "from urllib",
        "import requests",
        "import httpx",
        "import subprocess",
        "from subprocess",
        "gh pr",
        "gh api",
        "/repos/",
        "api.github.com",
        "GITHUB_TOKEN",
        "urlopen",
        "Request(",
    )
    for token in forbidden:
        assert token not in source, token
    assert "No GitHub mutation" in source or "no GitHub mutation" in source


def test_queued_never_counts_as_success() -> None:
    for status in sorted(QUEUED_STATUSES):
        assert classify_check(_check("Merge Readiness", status=status, conclusion="success"), current_sha=HEAD) == "queued"
        assert classify_check(_check("Merge Readiness", status=status, conclusion=None), current_sha=HEAD) == "queued"


def test_cancelled_never_counts_as_success() -> None:
    assert classify_check(_check("Merge Readiness", conclusion="cancelled"), current_sha=HEAD) == "blocking"
    assert classify_check(_check("Merge Readiness", conclusion="canceled"), current_sha=HEAD) == "blocking"
    assert classify_check(_check("Merge Readiness", conclusion="cancelled"), current_sha=HEAD) != "success"


def test_blocking_conclusions_are_blocking() -> None:
    for conclusion in sorted(BLOCKING_CONCLUSIONS):
        assert classify_check(_check("lint", conclusion=conclusion), current_sha=HEAD) == "blocking"


def test_success_on_current_sha_is_success() -> None:
    assert classify_check(_check("Merge Readiness"), current_sha=HEAD) == "success"


def test_old_sha_is_stale_not_success() -> None:
    assert classify_check(_check("Merge Readiness", head_sha="old"), current_sha=HEAD) == "stale"
    queued_old = _check("Merge Readiness", status="queued", conclusion=None, head_sha="old")
    assert classify_check(queued_old, current_sha=HEAD) == "stale"
    failed_old = _check("Merge Readiness", conclusion="failure", head_sha="old")
    assert classify_check(failed_old, current_sha=HEAD) == "stale"


def test_stale_conclusion_on_current_sha_is_stale() -> None:
    assert classify_check(_check("Merge Readiness", conclusion="stale"), current_sha=HEAD) == "stale"


def test_unknown_conclusion_fails_closed() -> None:
    assert classify_check(_check("Merge Readiness", conclusion="explode"), current_sha=HEAD) == "unknown"
    assert classify_check(_check("Merge Readiness", conclusion="mystery"), current_sha=HEAD) == "unknown"
    assert classify_check(_check("Merge Readiness", conclusion=""), current_sha=HEAD) == "unknown"
    completed_no_conclusion = {
        "name": "Merge Readiness",
        "status": "completed",
        "head_sha": HEAD,
    }
    assert classify_check(completed_no_conclusion, current_sha=HEAD) == "unknown"
    assert classify_check(["not", "an", "object"], current_sha=HEAD) == "unknown"
    assert classify_check(_check("Merge Readiness") | {"extra": True}, current_sha=HEAD) == "unknown"


def test_first_rollup_priority_is_blocking_queued_stale_success() -> None:
    assert first_rollup(["success", "queued", "blocking", "stale"]) == "blocking"
    assert first_rollup(["success", "stale", "queued"]) == "queued"
    assert first_rollup(["success", "stale"]) == "stale"
    assert first_rollup(["success", "success"]) == "success"
    assert first_rollup(["success", "unknown"]) == "unknown"
    assert first_rollup([]) == "unknown"
    assert first_rollup(["not-a-class"]) == "unknown"


def test_mixed_required_checks_use_first_blocking() -> None:
    report, errors = classify_document(
        _doc(
            required_checks=["unit", "lint", "Merge Readiness"],
            checks=[
                _check("unit"),
                _check("lint", conclusion="failure"),
                _check("Merge Readiness", status="queued", conclusion=None),
            ],
        )
    )
    assert errors == []
    assert report["rollup"] == "blocking"
    assert [row["class"] for row in report["check_states"]] == ["success", "blocking", "queued"]


def test_queued_required_check_rolls_up_before_stale_and_success() -> None:
    report, errors = classify_document(
        _doc(
            required_checks=["unit", "lint"],
            checks=[
                _check("unit"),
                _check("lint", status="in_progress", conclusion=None),
            ],
        )
    )
    assert errors == []
    assert report["rollup"] == "queued"


def test_stale_required_check_rolls_up_before_success() -> None:
    report, errors = classify_document(
        _doc(
            required_checks=["unit", "lint"],
            checks=[
                _check("unit"),
                _check("lint", conclusion="stale"),
            ],
        )
    )
    assert errors == []
    assert report["rollup"] == "stale"


def test_all_required_success_rolls_up_success() -> None:
    report, errors = classify_document(
        _doc(
            required_checks=["unit", "Merge Readiness"],
            checks=[_check("unit"), _check("Merge Readiness")],
        )
    )
    assert errors == []
    assert report["rollup"] == "success"
    assert report["owning_issue"] == "#969"
    assert report["repair"] is None
    assert report["pr_number"] == 42
    assert report["pr_state"] == "open"


def test_prefers_current_sha_when_duplicate_names_exist() -> None:
    report, errors = classify_document(
        _doc(
            required_checks=["Merge Readiness"],
            checks=[
                _check("Merge Readiness", conclusion="failure", head_sha="old"),
                _check("Merge Readiness"),
            ],
        )
    )
    assert errors == []
    assert report["rollup"] == "success"


def test_missing_required_check_fails_closed() -> None:
    report, errors = classify_document(_doc(required_checks=["Merge Readiness", "secret-scan"], checks=[_check("Merge Readiness")]))
    assert report["rollup"] == "unknown"
    assert any("pr-blocker-map unknown unclassified" in item for item in errors)
    assert any("secret-scan" in item for item in errors)


def test_unknown_document_conclusion_is_a_violation() -> None:
    report, errors = classify_document(
        _doc(checks=[_check("Merge Readiness", conclusion="nope")])
    )
    assert report["check_states"][0]["class"] == "unknown"
    assert report["rollup"] == "unknown"
    assert any("pr-blocker-map unknown unclassified" in item for item in errors)


def test_closed_pr_fails_closed() -> None:
    report, errors = classify_document(_doc(pull_request=_pr(state="closed")))
    assert report["rollup"] == "unknown" or any("pr-blocker-map unknown pr_state" in item for item in errors)
    assert any("pr-blocker-map unknown pr_state" in item for item in errors)


def test_unknown_fields_and_wrong_schema_fail_closed() -> None:
    errors = classify_document(_doc(severity="high", mutate=True))[1]
    assert any("pr-blocker-map unknown field" in item for item in errors)
    version_errors = classify_document(_doc(schema_version=2))[1]
    assert any("pr-blocker-map unknown schema_version" in item for item in version_errors)
    root_errors = classify_document(["not", "an", "object"])[1]
    assert root_errors == ["pr-blocker-map unknown root_type: document must be an object"]


def test_repair_and_owning_issue_are_preserved() -> None:
    report, errors = classify_document(
        _doc(pull_request=_pr(owning_issue="#969", repair="ci/merge-readiness"))
    )
    assert errors == []
    assert report["owning_issue"] == "#969"
    assert report["repair"] == "ci/merge-readiness"


def test_cli_accepts_success_fixture(tmp_path: Path, capsys) -> None:
    path = tmp_path / "pr-checks.json"
    path.write_text(json.dumps(_doc()), encoding="utf-8")
    assert main([str(path)]) == 0
    out = capsys.readouterr().out
    assert "rollup=success" in out
    assert "owning_issue=#969" in out


def test_cli_accepts_blocking_fixture_without_mutation(tmp_path: Path, capsys) -> None:
    path = tmp_path / "pr-checks.json"
    path.write_text(
        json.dumps(_doc(checks=[_check("Merge Readiness", conclusion="cancelled")])),
        encoding="utf-8",
    )
    assert main([str(path)]) == 0
    assert "rollup=blocking" in capsys.readouterr().out


def test_cli_rejects_unknown_conclusion(tmp_path: Path) -> None:
    path = tmp_path / "pr-checks.json"
    path.write_text(
        json.dumps(_doc(checks=[_check("Merge Readiness", conclusion="wat")])),
        encoding="utf-8",
    )
    assert main([str(path)]) == 1


def test_cli_rejects_missing_fixture(tmp_path: Path) -> None:
    missing = tmp_path / "absent.json"
    try:
        main([str(missing)])
    except SystemExit as exc:
        assert "pr-blocker-map unreadable missing_doc" in str(exc)
    else:
        raise AssertionError("missing fixture must fail closed")
