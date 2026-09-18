from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "arm64.yml"


def test_arm64_pr_close_is_zero_work_cancellation_tombstone() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "types: [opened, synchronize, reopened, closed]" in text
    assert 'group: arm64-${{ github.event.pull_request.number || github.ref }}' in text
    assert "cancel-in-progress: true" in text
    assert "if: github.event_name != 'pull_request' || github.event.action != 'closed'" in text
    assert "runs-on: ubuntu-24.04-arm" in text
