from __future__ import annotations

from pathlib import Path


def _workflow_text() -> str:
    root = Path(__file__).resolve().parents[2]
    return (root / ".github/workflows/queue-drain.yml").read_text(encoding="utf-8")


def test_queue_drain_does_not_self_thrash_on_main_pushes() -> None:
    workflow = _workflow_text()

    assert "workflow_dispatch:" in workflow
    assert "schedule:" in workflow
    assert "\n  push:\n" not in workflow
    assert 'cron: "2-57/5 * * * *"' in workflow
    assert "cancel-in-progress: false" in workflow


def test_queue_drain_keeps_recovery_safety_boundary() -> None:
    workflow = _workflow_text()

    assert "runs-on: ubuntu-latest" in workflow
    assert "actions: write" in workflow
    assert "contents: read" in workflow
    assert "permissions: {}" in workflow
    assert "control_plane_paths = frozenset" in workflow
    assert "'.github/workflows/queue-drain.yml'" in workflow
    assert "'.github/workflows/pr-obsolete-run-drain.yml'" in workflow
