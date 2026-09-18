from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

CLOSE_BARRIER_WORKFLOWS = (
    "artifact-policy.yml",
    "malware-gate.yml",
    "provenance-policy.yml",
    "codeql.yml",
    "pr-hygiene.yml",
    "workflow-input-security.yml",
)


def test_close_barrier_workflows_cancel_stranded_pr_runs_without_runner_work() -> None:
    for name in CLOSE_BARRIER_WORKFLOWS:
        text = (WORKFLOWS / name).read_text(encoding="utf-8")

        assert "closed" in text, f"{name} must listen for pull_request closed"
        assert "concurrency:" in text, f"{name} must use workflow concurrency"
        assert "cancel-in-progress:" in text, f"{name} must cancel the prior PR lane"
        assert "github.event.action != 'closed'" in text, (
            f"{name} must skip validation work on the close-only barrier run"
        )


def test_close_barriers_keep_normal_pr_lifecycle_events() -> None:
    for name in CLOSE_BARRIER_WORKFLOWS:
        text = (WORKFLOWS / name).read_text(encoding="utf-8")
        for action in ("opened", "synchronize", "reopened"):
            assert action in text, f"{name} lost normal PR action {action}"
