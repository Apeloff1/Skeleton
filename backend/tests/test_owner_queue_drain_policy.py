from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "queue-drain.yml"
OWNER_DRAIN = ROOT / "scripts" / "drain_actions_queue.sh"

CONTROL_PLANE_PATHS = {
    ".github/workflows/actions-housekeeping-cli.yml",
    ".github/workflows/branch-clean.yml",
    ".github/workflows/branch-archive.yml",
    ".github/workflows/branch-flow.yml",
    ".github/workflows/branch-repair-100.yml",
    ".github/workflows/merge-readiness.yml",
    ".github/workflows/pr-obsolete-run-drain.yml",
    ".github/workflows/queue-drain.yml",
    ".github/workflows/p1-evidence-identity.yml",
    ".github/workflows/p1-maturity-reconciliation.yml",
    ".github/workflows/p1-reproducibility-bundle.yml",
    ".github/workflows/p1-required-gate-authority.yml",
    ".github/workflows/p1-risk-evidence-binding.yml",
    ".github/workflows/p1-scope-freeze.yml",
}


def _workflow_path_literals(text: str) -> set[str]:
    return set(re.findall(r"['\"](\.github/workflows/[^'\"]+\.yml)['\"]", text))


def test_owner_queue_drain_keeps_canonical_control_plane_exclusions() -> None:
    canonical = WORKFLOW.read_text(encoding="utf-8")
    owner = OWNER_DRAIN.read_text(encoding="utf-8")

    def protected_paths(source: str) -> set[str]:
        # Capture only the protected set; periodic-controller coalescing is a
        # separate, narrowly guarded policy and must not affect this check.
        section = source.split("control_plane_paths = frozenset", 1)[1]
        section = section.split("}", 1)[0]
        return _workflow_path_literals(section)

    canonical_paths = protected_paths(canonical)
    owner_paths = protected_paths(owner)
    assert canonical_paths <= owner_paths
    assert ".github/workflows/automerge-control-plane.yml" in canonical_paths
    assert ".github/workflows/repair-intake.yml" in canonical_paths
    assert ".github/workflows/queue-drain.yml" in canonical_paths
    assert ".github/workflows/merge-readiness.yml" in owner_paths
    assert ".github/workflows/p1-required-gate-authority.yml" in owner_paths


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


def test_owner_queue_drain_rechecks_main_before_mutation() -> None:
    owner = OWNER_DRAIN.read_text(encoding="utf-8")

    recheck = owner.index("live_head = main_sha()")
    cancel = owner.index("status = cancel(run_id)")
    assert recheck < cancel
    assert "if live_head != head:" in owner
    assert "main advanced before mutation" in owner
    assert "deferring this pass" in owner
    assert "total_selected += len(selected)" in owner[recheck:cancel]
