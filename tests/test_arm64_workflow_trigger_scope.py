from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "arm64.yml"


def test_arm64_trigger_excludes_backend_test_only_changes_but_keeps_skeleton_tests() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert text.count('- "!backend/tests/**"') == 2
    assert '- "!skeleton/testing/**"' not in text
    assert text.count('- "backend/**"') == 2
    assert text.count('- "skeleton/**"') == 2


def test_arm64_runtime_and_workflow_changes_still_trigger() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    for path in (
        '"Dockerfile"',
        '"backend/**"',
        '"frontend/**"',
        '"skeleton/**"',
        '"pyproject.toml"',
        '"docker-compose.yml"',
        '".github/workflows/arm64.yml"',
    ):
        assert text.count(f"- {path}") == 2

    assert "runs-on: ubuntu-24.04-arm" in text


def test_arm64_trigger_keeps_test_modules_executed_by_legacy_runner() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    runner = (ROOT / "tests" / "run_unit.py").read_text(encoding="utf-8")

    assert "skeleton.testing.test_simulation_physics_" in runner
    assert '- "skeleton/**"' in workflow
    assert '- "!skeleton/testing/**"' not in workflow


def test_arm64_draft_transitions_cancel_without_consuming_runner() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert (
        "types: [opened, synchronize, reopened, ready_for_review, "
        "converted_to_draft, closed]"
    ) in text
    assert "github.event.pull_request.draft" in text
    assert "github.event.action != 'converted_to_draft'" in text
    assert "github.event.action != 'closed'" in text
    assert "cancel-in-progress: true" in text
