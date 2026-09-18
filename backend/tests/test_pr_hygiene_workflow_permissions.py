from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pr-hygiene.yml"


def test_pr_hygiene_uses_minimum_token_scope() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    # The classifier reads PR metadata/files, then mutates repository/PR labels
    # through the Issues labels API. It never edits PR state or metadata.
    assert "issues: write" in text
    assert "pull-requests: read" in text
    assert "pull-requests: write" not in text

    # Keep write authority away from fork pull requests and never execute head
    # content as part of classification.
    assert "github.event.pull_request.head.repo.full_name == github.repository" in text
    assert "actions/checkout" not in text

def test_pr_hygiene_runs_only_when_diff_identity_can_change() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "types: [opened, reopened, synchronize]" in text
    for metadata_only in (
        "edited",
        "ready_for_review",
        "converted_to_draft",
        "closed",
    ):
        assert metadata_only not in text



def test_pr_hygiene_uses_general_runner_capacity() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "runs-on: ubuntu-latest" in text
    assert "runs-on: ubuntu-24.04-arm" not in text
