from pathlib import Path

import pytest

from skeleton.automation.repair_intake import intake_fingerprint, issue_marker


def test_intake_fingerprint_is_deterministic_and_case_normalized() -> None:
    assert intake_fingerprint("CodeQL", "failure", "ABC123") == intake_fingerprint(
        "codeql", "FAILURE", "abc123"
    )


def test_intake_marker_accepts_only_sha256_identity() -> None:
    fingerprint = intake_fingerprint("CodeQL", "failure", "ABC123")
    assert issue_marker(fingerprint) == f"<!-- repair-intake:fingerprint={fingerprint} -->"

    with pytest.raises(ValueError, match="sha256"):
        issue_marker("../../not-a-digest-->")


def test_intake_identity_rejects_missing_fields() -> None:
    with pytest.raises(ValueError, match="workflow"):
        intake_fingerprint(" ", "failure", "abc123")
    with pytest.raises(TypeError, match="head_sha"):
        intake_fingerprint("CodeQL", "failure", None)  # type: ignore[arg-type]


def test_workflow_run_consumer_never_checks_out_triggering_code() -> None:
    workflow = Path(".github/workflows/repair-intake.yml").read_text(encoding="utf-8")

    assert "actions/checkout" not in workflow
    assert "github.event.workflow_run.head_repository.full_name == github.repository" in workflow
    assert 'os.environ["RUN_ID"].strip()' not in workflow
    assert "--state all" in workflow
    assert 'os.environ["HEAD_SHA"].strip().lower()' in workflow


def test_issue_body_template_cannot_escape_yaml_shell_block() -> None:
    workflow = Path(".github/workflows/repair-intake.yml").read_text(encoding="utf-8")

    assert "printf -v body '%s\\n'" in workflow
    assert "\n${marker}\n" not in workflow
    assert "\n- Workflow: ${RUN_NAME}\n" not in workflow
    assert "\nCorrelate this observation against existing findings" not in workflow
