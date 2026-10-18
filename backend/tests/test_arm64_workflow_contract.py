from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ACTIVE_WORKFLOW = ROOT / ".github" / "workflows" / "arm64.yml"
ARCHIVED_WORKFLOW = ROOT / ".github" / "workflows-archive" / "arm64.yml"
WORKFLOW = ACTIVE_WORKFLOW if ACTIVE_WORKFLOW.is_file() else ARCHIVED_WORKFLOW


def test_arm64_is_manual_only_when_specialized() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    # This expensive specialized lane is explicitly dispatched, not a PR fanout.
    assert "  workflow_dispatch:" in text
    assert "  pull_request:" not in text
    assert "  push:" not in text
    assert "  schedule:" not in text
    assert 'group: arm64-${{ github.event.pull_request.number || github.ref }}' in text
    assert "cancel-in-progress: true" in text
    assert "github.event_name != 'pull_request' ||" in text
    assert "!github.event.pull_request.draft" in text
    assert "github.event.action != 'converted_to_draft'" in text
    assert "github.event.action != 'closed'" in text
    assert "runs-on: ubuntu-24.04-arm" in text
