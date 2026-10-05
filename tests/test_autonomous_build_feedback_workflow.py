from pathlib import Path

WORKFLOW = Path(".github/workflows/autonomous-build-feedback.yml")
GOOD_PIN = "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1"
BAD_PIN = "actions/upload-artifact@ea165f8d65b6e75b5404495eeb8b5cf9c8f1f1a2"


def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_autonomous_build_feedback_uses_resolvable_node24_upload_artifact_pin() -> None:
    text = workflow_text()
    assert GOOD_PIN in text
    assert BAD_PIN not in text


def test_autonomous_build_feedback_coalesces_by_exact_tested_head() -> None:
    text = workflow_text()
    assert (
        "group: autonomous-build-feedback-${{ github.event.workflow_run.head_sha }}"
        in text
    )
    assert "cancel-in-progress: true" in text
    assert "github.event.workflow_run.head_branch" not in text.split(
        "permissions:", 1
    )[0]


def test_autonomous_build_feedback_rejects_non_pr_and_untrusted_sources() -> None:
    text = workflow_text()
    assert "github.event.workflow_run.event == 'pull_request'" in text
    assert (
        "github.event.workflow_run.head_repository.full_name == github.repository"
        in text
    )
    assert "github.event.workflow_run.conclusion != 'cancelled'" in text
    assert "github.event.workflow_run.conclusion != 'skipped'" in text
