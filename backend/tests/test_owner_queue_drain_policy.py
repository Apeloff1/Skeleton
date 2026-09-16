from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "queue-drain.yml"
OWNER_DRAIN = ROOT / "scripts" / "drain_actions_queue.sh"

CONTROL_PLANE_PATHS = {
    ".github/workflows/branch-clean.yml",
    ".github/workflows/branch-flow.yml",
    ".github/workflows/branch-repair-100.yml",
    ".github/workflows/merge-readiness.yml",
    ".github/workflows/pr-obsolete-run-drain.yml",
    ".github/workflows/queue-drain.yml",
}


def _workflow_path_literals(text: str) -> set[str]:
    return set(re.findall(r"['\"](\.github/workflows/[^'\"]+\.yml)['\"]", text))


def test_owner_queue_drain_keeps_canonical_control_plane_exclusions() -> None:
    canonical = WORKFLOW.read_text(encoding="utf-8")
    owner = OWNER_DRAIN.read_text(encoding="utf-8")

    assert _workflow_path_literals(canonical) == CONTROL_PLANE_PATHS
    assert _workflow_path_literals(owner) == CONTROL_PLANE_PATHS


def test_owner_queue_drain_is_bounded_and_dry_run_by_default() -> None:
    owner = OWNER_DRAIN.read_text(encoding="utf-8")

    assert 'mode="${1:---dry-run}"' in owner
    assert 'max_cancel="${MAX_CANCEL:-500}"' in owner
    assert 'export DRY_RUN=1' in owner
    assert 'path(run).startswith("dynamic/")' in owner
    assert 'run_status="queued"' in owner
    assert 'run_status="in_progress"' in owner
    assert '"X-GitHub-Api-Version": "2026-03-10"' in owner


def test_owner_queue_drain_requires_current_main_replacement_before_stale_dynamic_cancel() -> None:
    owner = OWNER_DRAIN.read_text(encoding="utf-8")

    assert "replacement_keys =" in owner
    assert "workflow_event_key(run) in replacement_keys" in owner
    assert 'and (run.get("head_sha") or "") != head' in owner
