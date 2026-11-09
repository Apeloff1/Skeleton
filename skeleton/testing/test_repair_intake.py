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
            failed_run_id=500,
            workflow_id="4242",  # type: ignore[arg-type]
            opener=lambda _path: (200, {"total_count": 0, "workflow_runs": []}),
        )
    with pytest.raises(ValueError, match="workflow_id"):
        workflow_sha_recovered(
            "Apeloff1/Skeleton",
            "Merge Readiness",
            HEAD_SHA,
            failed_run_id=500,
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


def test_retired_repair_intake_cannot_auto_admit_workflow_runs() -> None:
    # The legacy workflow_run consumer was retired to preserve the bounded
    # automatic workflow admission surface. Do not silently reactivate it.
    assert not Path(".github/workflows/repair-intake.yml").exists()
    traffic = Path(".github/workflows/automation-traffic-manager.yml").read_text(
        encoding="utf-8"
    )
    assert "workflow_run:" not in traffic
    assert "repair-intake.yml" not in traffic
    assert "permissions: {}" in traffic
    assert "cancel-in-progress: false" in traffic


def test_active_traffic_admission_stays_default_branch_and_policy_bound() -> None:
    traffic = Path(".github/workflows/automation-traffic-manager.yml").read_text(
        encoding="utf-8"
    )
    assert 'test "$TRAFFIC_EVENT_REF" = "$TRAFFIC_EXPECTED_REF"' in traffic
    assert "if: ${{ needs.admission.outputs.admit == 'true' }}" in traffic
    assert "Queue admitted repository supervisor" in traffic
    assert "actions: write" in traffic
