from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "pr-automation-index.yml"


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_pr_automation_reacts_only_to_terminal_workflow_state() -> None:
    text = _workflow_text()

    assert "types: [completed]" in text
    assert "types: [requested, in_progress, completed]" not in text
    assert "types: [requested]" not in text
    assert "types: [in_progress]" not in text


def test_pr_automation_keeps_required_trigger_coverage() -> None:
    text = _workflow_text()

    for workflow_name in (
        "Merge Readiness",
        "CI/CD",
        "Backend Quality",
        "Dependency Review",
        "Dependency Security",
        "CodeQL",
    ):
        assert f"- {workflow_name}" in text

    assert "schedule:" in text
    assert "workflow_dispatch:" in text
    assert 'branches:\n      - "*"\n      - "**"' in text
    assert "--head-sha" in text
    assert "--pr-hints-json" in text
    assert "toJSON(github.event.workflow_run.pull_requests.*.number)" in text
    assert "pull_requests[0]" not in text
