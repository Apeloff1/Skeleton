from pathlib import Path

import pytest

from skeleton.automation.repair_intake import (
    INTAKE_CREATE,
    INTAKE_SKIP_DUPLICATE,
    INTAKE_SKIP_FAMILY,
    INTAKE_SKIP_INVALID,
    INTAKE_SKIP_RECOVERED,
    INTAKE_SKIP_SUPERSEDED,
    INTAKE_SKIP_UNREADABLE,
    classify_intake,
    encode_branch_path,
    family_fingerprint,
    intake_fingerprint,
    issue_family_marker,
    issue_marker,
    resolve_branch_tip,
    workflow_sha_recovered,
)


def test_intake_fingerprint_is_deterministic_and_case_normalized() -> None:
    assert intake_fingerprint("CodeQL", "failure", "ABC123") == intake_fingerprint(
        "codeql", "FAILURE", "abc123"
    )


def test_family_fingerprint_groups_branch_not_sha_and_stays_distinct() -> None:
    family = family_fingerprint("Merge Readiness", "fix/core-package")
    other_sha = intake_fingerprint("Merge Readiness", "failure", "abc123")
    other_branch = family_fingerprint("Merge Readiness", "fix/other")
    other_workflow = family_fingerprint("CodeQL", "fix/core-package")

    assert family == family_fingerprint("merge readiness", "FIX/core-package")
    assert family != other_sha
    assert family != other_branch
    assert family != other_workflow
    assert issue_family_marker(family) == f"<!-- repair-intake:family={family} -->"


def test_intake_marker_accepts_only_sha256_identity() -> None:
    fingerprint = intake_fingerprint("CodeQL", "failure", "ABC123")
    assert issue_marker(fingerprint) == f"<!-- repair-intake:fingerprint={fingerprint} -->"

    with pytest.raises(ValueError, match="sha256"):
        issue_marker("../../not-a-digest-->")
    with pytest.raises(ValueError, match="sha256"):
        issue_family_marker("not-a-digest")


def test_intake_identity_rejects_missing_fields() -> None:
    with pytest.raises(ValueError, match="workflow"):
        intake_fingerprint(" ", "failure", "abc123")
    with pytest.raises(TypeError, match="head_sha"):
        intake_fingerprint("CodeQL", "failure", None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="control"):
        family_fingerprint("Merge Readiness", "fix/core\npackage")
    with pytest.raises(ValueError, match="maximum length"):
        family_fingerprint("Merge Readiness", "x" * 256)


def test_encode_branch_path_percent_encodes_slashes() -> None:
    assert encode_branch_path("fix/core-package") == "fix%2Fcore-package"


def test_resolve_branch_tip_is_fail_closed() -> None:
    def opener(path: str) -> tuple[int, dict[str, object] | None]:
        assert path == "/repos/Apeloff1/Skeleton/branches/fix%2Fcore-package"
        return 200, {"commit": {"sha": "abc123"}}

    state, sha = resolve_branch_tip("Apeloff1/Skeleton", "fix/core-package", opener=opener)
    assert state == "ok"
    assert sha == "abc123"

    assert resolve_branch_tip(
        "Apeloff1/Skeleton",
        "gone",
        opener=lambda _path: (404, None),
    ) == ("missing", None)
    assert resolve_branch_tip(
        "Apeloff1/Skeleton",
        "broken",
        opener=lambda _path: (_ for _ in ()).throw(TimeoutError("boom")),
    ) == ("unreadable", None)
    assert resolve_branch_tip(
        "Apeloff1/Skeleton",
        "odd",
        opener=lambda _path: (200, {"commit": {"sha": 12}}),
    ) == ("unreadable", None)


def test_classify_intake_preempts_storms_and_ambiguous_state() -> None:
    head = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

    assert (
        classify_intake(
            sha_record_exists=True,
            family_open_exists=False,
            branch_lookup="ok",
            branch_tip=head,
            head_sha=head,
        )
        == INTAKE_SKIP_DUPLICATE
    )
    assert (
        classify_intake(
            sha_record_exists=False,
            family_open_exists=False,
            branch_lookup="ok",
            branch_tip="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            head_sha=head,
        )
        == INTAKE_SKIP_SUPERSEDED
    )
    assert (
        classify_intake(
            sha_record_exists=False,
            family_open_exists=False,
            branch_lookup="missing",
            branch_tip=None,
            head_sha=head,
        )
        == INTAKE_SKIP_SUPERSEDED
    )
    assert (
        classify_intake(
            sha_record_exists=False,
            family_open_exists=False,
            branch_lookup="unreadable",
            branch_tip=None,
            head_sha=head,
        )
        == INTAKE_SKIP_UNREADABLE
    )
    assert (
        classify_intake(
            sha_record_exists=False,
            family_open_exists=True,
            branch_lookup="ok",
            branch_tip=head,
            head_sha=head,
        )
        == INTAKE_SKIP_FAMILY
    )
    assert (
        classify_intake(
            sha_record_exists=False,
            family_open_exists=False,
            branch_lookup="ok",
            branch_tip=head,
            head_sha=head,
        )
        == INTAKE_CREATE
    )
    assert (
        classify_intake(
            sha_record_exists=False,
            family_open_exists=False,
            branch_lookup="ok",
            branch_tip=head,
            head_sha=" ",
        )
        == INTAKE_SKIP_INVALID
    )
    assert (
        classify_intake(
            sha_record_exists=False,
            family_open_exists=False,
            branch_lookup="ok",
            branch_tip=head,
            head_sha=head,
            recovered=True,
        )
        == INTAKE_SKIP_RECOVERED
    )
    assert (
        classify_intake(
            sha_record_exists=False,
            family_open_exists=True,
            branch_lookup="ok",
            branch_tip=head,
            head_sha=head,
            recovered=False,
            recovery_known=False,
        )
        == INTAKE_SKIP_UNREADABLE
    )


def _recovery_opener(payload: dict[str, object], paths: list[str]):
    def opener(path: str) -> tuple[int, dict[str, object] | None]:
        paths.append(path)
        return 200, payload

    return opener


def test_workflow_sha_recovered_ignores_cancelled_and_foreign_workflows() -> None:
    payload = {
        "total_count": 3,
        "workflow_runs": [
            {"name": "Malware Gate", "conclusion": "cancelled"},
            {"name": "Merge Readiness", "conclusion": "failure"},
            {"name": "Merge Readiness", "conclusion": "success"},
        ],
    }
    paths: list[str] = []
    assert (
        workflow_sha_recovered(
            "Apeloff1/Skeleton",
            "Merge Readiness",
            "abc123",
            workflow_id=4242,
            opener=_recovery_opener(payload, paths),
        )
        is True
    )
    assert paths == [
        "/repos/Apeloff1/Skeleton/actions/workflows/4242/runs"
        "?head_sha=abc123&status=completed&per_page=100&page=1"
    ]
    assert (
        workflow_sha_recovered(
            "Apeloff1/Skeleton",
            "Malware Gate",
            "abc123",
            workflow_id=4242,
            opener=lambda _path: (200, payload),
        )
        is False
    )
    assert (
        workflow_sha_recovered(
            "Apeloff1/Skeleton",
            "Merge Readiness",
            "abc123",
            workflow_id=4242,
            opener=lambda _path: (500, None),
        )
        is None
    )


def test_workflow_sha_recovered_finds_success_beyond_first_thirty_results() -> None:
    failure = {"name": "Merge Readiness", "conclusion": "failure"}
    first_page = {"total_count": 31, "workflow_runs": [failure] * 30}
    second_page = {
        "total_count": 31,
        "workflow_runs": [{"name": "Merge Readiness", "conclusion": "success"}],
    }
    paths: list[str] = []

    def opener(path: str) -> tuple[int, dict[str, object] | None]:
        paths.append(path)
        if "page=1" in path:
            return 200, first_page
        if "page=2" in path:
            return 200, second_page
        raise AssertionError(f"unexpected recovery path: {path}")

    assert (
        workflow_sha_recovered(
            "Apeloff1/Skeleton",
            "Merge Readiness",
            "abc123",
            workflow_id=4242,
            opener=opener,
            page_size=30,
            max_pages=10,
        )
        is True
    )
    assert paths == [
        "/repos/Apeloff1/Skeleton/actions/workflows/4242/runs"
        "?head_sha=abc123&status=completed&per_page=30&page=1",
        "/repos/Apeloff1/Skeleton/actions/workflows/4242/runs"
        "?head_sha=abc123&status=completed&per_page=30&page=2",
    ]


def test_workflow_sha_recovered_fails_closed_when_page_bound_exhausted() -> None:
    failure_page = {
        "total_count": 250,
        "workflow_runs": [{"name": "Merge Readiness", "conclusion": "failure"}] * 100,
    }
    paths: list[str] = []

    def opener(path: str) -> tuple[int, dict[str, object] | None]:
        paths.append(path)
        return 200, failure_page

    assert (
        workflow_sha_recovered(
            "Apeloff1/Skeleton",
            "Merge Readiness",
            "abc123",
            workflow_id=4242,
            opener=opener,
            page_size=100,
            max_pages=2,
        )
        is None
    )
    assert len(paths) == 2
    assert "page=2" in paths[-1]


def test_workflow_sha_recovered_rejects_invalid_workflow_identity() -> None:
    with pytest.raises(TypeError, match="workflow_id"):
        workflow_sha_recovered(
            "Apeloff1/Skeleton",
            "Merge Readiness",
            "abc123",
            workflow_id="Merge Readiness",  # type: ignore[arg-type]
            opener=lambda _path: (200, {"total_count": 0, "workflow_runs": []}),
        )
    with pytest.raises(ValueError, match="workflow_id"):
        workflow_sha_recovered(
            "Apeloff1/Skeleton",
            "Merge Readiness",
            "abc123",
            workflow_id=0,
            opener=lambda _path: (200, {"total_count": 0, "workflow_runs": []}),
        )


def test_workflow_run_consumer_never_checks_out_triggering_code() -> None:
    workflow = Path(".github/workflows/repair-intake.yml").read_text(encoding="utf-8")

    assert "actions/checkout" not in workflow
    assert "github.event.workflow_run.head_repository.full_name == github.repository" in workflow
    assert 'os.environ["RUN_ID"].strip()' not in workflow
    assert "--state all" in workflow
    assert 'os.environ["HEAD_SHA"].strip().lower()' in workflow
    assert "github.event.workflow_run.workflow_id" in workflow
    assert "/actions/workflows/{workflow_id}/runs" in workflow
    assert "/actions/runs?" not in workflow
    assert "per_page=30" not in workflow
    assert "&page={page}" in workflow
    assert 'decision = "skip_unreadable"' in workflow


def test_workflow_preempts_superseded_sha_and_open_family_records() -> None:
    workflow = Path(".github/workflows/repair-intake.yml").read_text(encoding="utf-8")

    assert '"family"' in workflow
    assert "urllib.parse.quote" in workflow
    assert "skip_superseded" in workflow
    assert "skip_family" in workflow
    assert "skip_unreadable" in workflow
    assert "skip_recovered" in workflow
    assert "head_sha=" in workflow
    assert "--state open" in workflow
    assert "repair-intake:family=" in workflow
    assert "User-Agent': 'skeleton-repair-intake'" in workflow or 'User-Agent": "skeleton-repair-intake"' in workflow or "skeleton-repair-intake" in workflow


def test_issue_body_template_cannot_escape_yaml_shell_block() -> None:
    workflow = Path(".github/workflows/repair-intake.yml").read_text(encoding="utf-8")

    assert "printf -v body '%s\\n'" in workflow
    assert "\n${marker}\n" not in workflow
    assert "\n- Workflow: ${RUN_NAME}\n" not in workflow
    assert "\nCorrelate this observation against existing findings" not in workflow
