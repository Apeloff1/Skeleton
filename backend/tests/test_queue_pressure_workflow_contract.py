from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"

READY_ON_TRANSITION = (
    "merge-readiness.yml",
    "ci.yml",
    "backend-quality.yml",
    "frontier-contracts.yml",
    "artifact-policy.yml",
    "provenance-policy.yml",
    "malware-gate.yml",
)

DIFF_ONLY = (
    "repository-hygiene-gate.yml",
    "dependency-review.yml",
    "secret-scanning.yml",
)


def test_heavy_pr_gates_do_not_enqueue_noop_close_or_redraft_runs() -> None:
    for name in READY_ON_TRANSITION:
        text = (WORKFLOWS / name).read_text(encoding="utf-8")
        assert "types: [opened, synchronize, reopened, ready_for_review]" in text

    for name in DIFF_ONLY:
        text = (WORKFLOWS / name).read_text(encoding="utf-8")
        assert "types: [opened, synchronize, reopened]" in text


def test_obsolete_run_recovery_is_one_repository_wide_lane() -> None:
    text = (WORKFLOWS / "pr-obsolete-run-drain.yml").read_text(encoding="utf-8")

    assert "group: pr-run-drain-${{ github.repository }}" in text
    assert "cancel-in-progress: false" in text
    assert text.count("python backend/scripts/pr_obsolete_run_sweep.py") == 2
    assert text.count("MAX_CANCELLATIONS: '250'") == 2
