from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "arm64.yml"


def test_arm64_trigger_excludes_test_only_backend_and_skeleton_changes() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert text.count('- "!backend/tests/**"') == 2
    assert text.count('- "!skeleton/testing/**"') == 2
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
