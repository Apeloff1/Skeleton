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

HEAD_SHA = "0123456789abcdef0123456789abcdef01234567"
OTHER_SHA = "fedcba9876543210fedcba9876543210fedcba98"


def test_intake_fingerprint_is_deterministic_and_case_normalized() -> None:
    assert intake_fingerprint("CodeQL", "failure", HEAD_SHA.upper()) == intake_fingerprint(
        "codeql", "FAILURE", HEAD_SHA
    )


def test_family_fingerprint_preserves_case_sensitive_git_ref_identity() -> None:
    upper = family_fingerprint("Merge Readiness", "fix/Core")
    lower = family_fingerprint("merge readiness", "fix/core")

    assert upper != lower
    assert upper == family_fingerprint("MERGE READINESS", "fix/Core")
    assert issue_family_marker(upper) == f"<!-- repair-intake:family={upper} -->"


def test_intake_markers_accept_only_sha256_identity() -> None:
    fingerprint = intake_fingerprint("CodeQL", "failure", HEAD_SHA)
    assert issue_marker(fingerprint) == f"<!-- repair-intake:fingerprint={fingerprint} -->"

    with pytest.raises(ValueError, match="sha256"):
        issue_marker("../../not-a-digest-->")
    with pytest.raises(ValueError, match="sha256"):
        issue_family_marker("not-a-digest")


def test_intake_identity_rejects_missing_or_noncanonical_fields() -> None:
    with pytest.raises(ValueError, match="workflow"):
        intake_fingerprint(" ", "failure", HEAD_SHA)
    with pytest.raises(TypeError, match="head_sha"):
        intake_fingerprint("CodeQL", "failure", None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="canonical"):
        family_fingerprint("Merge Readiness", " fix/core")
    with pytest.raises(ValueError, match="control"):
        family_fingerprint("Merge Readiness", "fix/core\npackage")
    with pytest.raises(ValueError, match="maximum length"):
        family_fingerprint("Merge Readiness", "x" * 256)


@pytest.mark.parametrize(
    "head_sha",
    [
        HEAD_SHA[:-1],
        HEAD_SHA + "a",
        HEAD_SHA[:7],
        f" {HEAD_SHA}",
        f"{HEAD_SHA} ",
        "abc123",
        "g" * 40,
    ],
)
def test_intake_fingerprint_rejects_malformed_head_sha(head_sha: str) -> None:
    with pytest.raises(ValueError, match="40-character hex commit OID"):
        intake_fingerprint("CodeQL", "failure", head_sha)


def test_encode_branch_path_percent_encodes_slashes_without_case_folding() -> None:
    assert encode_branch_path("Fix/Core") == "Fix%2FCore"


def test_resolve_branch_tip_is_strict_and_fail_closed() -> None:
    paths: list[str] = []

    def opener(path: str) -> tuple[int, dict[str, object] | None]:
        paths.append(path)
        return 200, {"commit": {"sha": HEAD_SHA.upper()}}

    assert resolve_branch_tip(
        "Apeloff1/Skeleton",
        "Fix/Core",
        opener=opener,
    ) == ("ok", HEAD_SHA)
    assert paths == ["/repos/Apeloff1/Skeleton/branches/Fix%2FCore"]

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
        "bad-tip",
        opener=lambda _path: (200, {"commit": {"sha": "abc123"}}),
    ) == ("unreadable", None)


def test_workflow_sha_recovered_uses_workflow_specific_bounded_pagination() -> None:
    failure = {"id": 500, "name": "Merge Readiness", "conclusion": "failure"}
    first_page = {"total_count": 31, "workflow_runs": [failure] * 30}
    second_page = {
        "total_count": 31,
        "workflow_runs": [{"id": 501, "name": "Merge Readiness", "conclusion": "success"}],
    }
    paths: list[str] = []

    def opener(path: str) -> tuple[int, dict[str, object] | None]:
        paths.append(path)
        if "page=1" in path:
            return 200, first_page
        if "page=2" in path:
            return 200, second_page
        raise AssertionError(f"unexpected path: {path}")

    assert (
        workflow_sha_recovered(
            "Apeloff1/Skeleton",
            "Merge Readiness",
            HEAD_SHA,
            workflow_id=4242,
            failed_run_id=500,
            opener=opener,
            page_size=30,
            max_pages=10,
        )
        is True
    )
    assert paths == [
        f"/repos/Apeloff1/Skeleton/actions/workflows/4242/runs?head_sha={HEAD_SHA}&status=completed&per_page=30&page=1",
        f"/repos/Apeloff1/Skeleton/actions/workflows/4242/runs?head_sha={HEAD_SHA}&status=completed&per_page=30&page=2",
    ]


def test_workflow_sha_recovered_ignores_success_older_than_failure() -> None:
    payload = {
        "total_count": 1,
        "workflow_runs": [
            {"id": 499, "name": "Merge Readiness", "conclusion": "success"}
        ],
    }
    assert workflow_sha_recovered(
        "Apeloff1/Skeleton",
        "Merge Readiness",
        HEAD_SHA,
        workflow_id=4242,
        failed_run_id=500,
        opener=lambda _path: (200, payload),
    ) is False


def test_workflow_sha_recovered_fails_closed_on_incomplete_or_unreadable_scan() -> None:
    page = {
        "total_count": 250,
        "workflow_runs": [{"id": 500, "name": "Merge Readiness", "conclusion": "failure"}] * 100,
    }

    assert (
        workflow_sha_recovered(
            "Apeloff1/Skeleton",
            "Merge Readiness",
            HEAD_SHA,
            workflow_id=4242,
            failed_run_id=500,
            opener=lambda _path: (200, page),
            page_size=100,
            max_pages=2,
        )
        is None
    )
    assert (
        workflow_sha_recovered(
            "Apeloff1/Skeleton",
            "Merge Readiness",
            HEAD_SHA,
            workflow_id=4242,
            failed_run_id=500,
            opener=lambda _path: (500, None),
        )
        is None
    )


def test_workflow_sha_recovered_rejects_invalid_workflow_identity() -> None:
    with pytest.raises(TypeError, match="workflow_id"):
        workflow_sha_recovered(
            "Apeloff1/Skeleton",
            "Merge Readiness",
            HEAD_SHA,
            workflow_id="4242",  # type: ignore[arg-type]
            opener=lambda _path: (200, {"total_count": 0, "workflow_runs": []}),
        )
    with pytest.raises(ValueError, match="workflow_id"):
        workflow_sha_recovered(
            "Apeloff1/Skeleton",
            "Merge Readiness",
            HEAD_SHA,
            workflow_id=0,
            opener=lambda _path: (200, {"total_count": 0, "workflow_runs": []}),
        )


def test_classify_intake_preempts_duplicate_stale_recovered_and_family_work() -> None:
    assert (
        classify_intake(
            sha_record_exists=True,
            family_open_exists=False,
            branch_lookup="ok",
            branch_tip=HEAD_SHA,
            head_sha=HEAD_SHA,
        )
        == INTAKE_SKIP_DUPLICATE
    )
    assert (
        classify_intake(
            sha_record_exists=False,
            family_open_exists=False,
            branch_lookup="ok",
            branch_tip=OTHER_SHA,
            head_sha=HEAD_SHA,
        )
        == INTAKE_SKIP_SUPERSEDED
    )
    assert (
        classify_intake(
            sha_record_exists=False,
            family_open_exists=False,
            branch_lookup="missing",
            branch_tip=None,
            head_sha=HEAD_SHA,
        )
        == INTAKE_SKIP_SUPERSEDED
    )
    assert (
        classify_intake(
            sha_record_exists=False,
            family_open_exists=False,
            branch_lookup="unreadable",
            branch_tip=None,
            head_sha=HEAD_SHA,
        )
        == INTAKE_SKIP_UNREADABLE
    )
    assert (
        classify_intake(
            sha_record_exists=False,
            family_open_exists=False,
            branch_lookup="ok",
            branch_tip=HEAD_SHA,
            head_sha=HEAD_SHA,
            recovered=True,
        )
        == INTAKE_SKIP_RECOVERED
    )
    assert (
        classify_intake(
            sha_record_exists=False,
            family_open_exists=True,
            branch_lookup="ok",
            branch_tip=HEAD_SHA,
            head_sha=HEAD_SHA,
        )
        == INTAKE_SKIP_FAMILY
    )
    assert (
        classify_intake(
            sha_record_exists=False,
            family_open_exists=False,
            branch_lookup="ok",
            branch_tip=HEAD_SHA,
            head_sha=HEAD_SHA,
        )
        == INTAKE_CREATE
    )
    assert (
        classify_intake(
            sha_record_exists=False,
            family_open_exists=False,
            branch_lookup="ok",
            branch_tip=HEAD_SHA,
            head_sha="abc123",
        )
        == INTAKE_SKIP_INVALID
    )


def test_workflow_run_trigger_surface_is_bounded() -> None:
    workflow = Path(".github/workflows/repair-intake.yml").read_text(encoding="utf-8")

    assert "- Merge Readiness" in workflow
    assert "- Malware Gate" in workflow
    for workflow_name in ("CodeQL", "Dependency Review", "Repository Hygiene Gate"):
        assert f"- {workflow_name}" not in workflow


def test_workflow_concurrency_coalesces_superseded_pr_failures() -> None:
    workflow = Path(".github/workflows/repair-intake.yml").read_text(encoding="utf-8")

    assert (
        "group: repair-intake-${{ github.event.workflow_run.workflow_id }}-"
        "${{ join(github.event.workflow_run.pull_requests.*.number, '-') || "
        "github.event.workflow_run.head_sha }}"
    ) in workflow
    assert "cancel-in-progress: true" in workflow
    assert "github.event.workflow_run.pull_requests[0]" not in workflow


def test_workflow_run_consumer_never_checks_out_triggering_code() -> None:
    workflow = Path(".github/workflows/repair-intake.yml").read_text(encoding="utf-8")

    assert "actions/checkout" not in workflow
    assert "github.event.workflow_run.head_repository.full_name == github.repository" in workflow
    assert 'branches:\n      - "*"\n      - "**"' in workflow
    assert "toJSON(github.event.workflow_run.pull_requests.*.number)" in workflow
    assert "github.event.workflow_run.workflow_id" in workflow
    assert 'os.environ["HEAD_SHA"].casefold()' in workflow
    assert r'^[0-9a-f]{40}$' in workflow
    assert "workflow_run head SHA must be a 40-character hex commit OID" in workflow
    assert "workflow_run head branch must be a canonical Git ref name" in workflow
    assert "pull_requests[0]" not in workflow


def test_workflow_preempts_stale_recovered_and_duplicate_family_queue_work() -> None:
    workflow = Path(".github/workflows/repair-intake.yml").read_text(encoding="utf-8")

    assert "/actions/workflows/{workflow_id}/runs" in workflow
    assert "/actions/runs?" not in workflow
    assert "per_page={page_size}&page={page}" in workflow
    assert "skip_superseded" in workflow
    assert "skip_recovered" in workflow
    assert "skip_unreadable" in workflow
    assert "skip_duplicate" in workflow
    assert "skip_family" in workflow
    assert "--state open" in workflow
    assert "repair-intake:family=" in workflow
    assert "head_branch.casefold()" not in workflow
    assert "head_branch.lower()" not in workflow
    assert '"family", head_branch' in workflow
    assert "repair-intake fingerprint search exceeded bounded identity scan" in workflow
    assert "repair-intake family search exceeded bounded identity scan" in workflow
    assert "candidate_id > current_run_id" in workflow


def test_issue_body_template_cannot_escape_yaml_shell_block() -> None:
    workflow = Path(".github/workflows/repair-intake.yml").read_text(encoding="utf-8")

    assert "printf -v body '%s\\n'" in workflow
    assert "\n${marker}\n" not in workflow
    assert "\n- Workflow: ${RUN_NAME}\n" not in workflow
    assert "\nCorrelate this observation against existing findings" not in workflow
