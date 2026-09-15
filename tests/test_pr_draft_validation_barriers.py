from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

HEAVY_DRAFT_AWARE_WORKFLOWS = {
    "backend-quality.yml": 1,
    "frontier-contracts.yml": 1,
    "merge-readiness.yml": 5,
    "ci.yml": 7,
}


def test_heavy_pr_validation_defers_drafts_and_restarts_when_ready() -> None:
    for name, minimum_guard_count in HEAVY_DRAFT_AWARE_WORKFLOWS.items():
        text = (WORKFLOWS / name).read_text(encoding="utf-8")

        for action in (
            "opened",
            "synchronize",
            "reopened",
            "ready_for_review",
            "converted_to_draft",
            "closed",
        ):
            assert action in text, f"{name} lost required PR lifecycle action {action}"

        assert "concurrency:" in text, f"{name} must retain per-PR concurrency"
        assert "github.event.pull_request.number" in text, (
            f"{name} must keep all PR lifecycle events in the same concurrency lane"
        )
        assert "github.event.pull_request.draft" in text, (
            f"{name} must skip heavy runner work while a PR is draft"
        )
        assert "github.event.action != 'converted_to_draft'" in text, (
            f"{name} must make draft conversion a cancellation-only barrier"
        )
        assert "github.event.action != 'closed'" in text, (
            f"{name} must make PR close a cancellation-only barrier"
        )
        assert text.count("github.event.pull_request.draft") >= minimum_guard_count, (
            f"{name} does not guard every heavy validation job"
        )


def test_ci_docker_publish_remains_main_only() -> None:
    text = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    assert "if: github.ref == 'refs/heads/main'" in text
