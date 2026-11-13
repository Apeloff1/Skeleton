from __future__ import annotations

from pathlib import Path
from runpy import run_path


ROOT = Path(__file__).resolve().parents[2]
# Backend CI executes from backend/, where backend/scripts shadows the root
# scripts package. Load the canonical tier parser by its checked-out path so
# this contract does not depend on the test runner's working directory.
events = run_path(str(ROOT / "scripts" / "check_ci_workflow_tiers.py"))["events"]
ACTIVE_WORKFLOW = ROOT / ".github" / "workflows" / "arm64.yml"
ARCHIVED_WORKFLOW = ROOT / ".github" / "workflows-archive" / "arm64.yml"
WORKFLOW = ACTIVE_WORKFLOW if ACTIVE_WORKFLOW.is_file() else ARCHIVED_WORKFLOW


def test_arm64_is_manual_only_when_specialized() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    # This expensive specialized lane is explicitly dispatched, not a PR fanout.
    # Only the top-level on: block declares workflow triggers. A Docker
    # build-push-action with push: false is not an Actions push event.
    assert events(text) == {"workflow_dispatch"}
    assert not ACTIVE_WORKFLOW.exists()  # archived manual evidence is not a passing live gate
    assert 'group: arm64-${{ github.event.pull_request.number || github.ref }}' in text
    assert "cancel-in-progress: true" in text
    assert "github.event_name != 'pull_request' ||" in text
    assert "!github.event.pull_request.draft" in text
    assert "github.event.action != 'converted_to_draft'" in text
    assert "github.event.action != 'closed'" in text
    assert "runs-on: ubuntu-24.04-arm" in text
