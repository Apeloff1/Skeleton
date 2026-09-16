from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci-failure-bot.yml"


def test_ci_failure_bot_remains_read_only_and_uses_trusted_code() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    # The implementation only observes Actions metadata. Keep its token at the
    # minimum permissions required for `gh run list` and repository checkout.
    assert "contents: read" in text
    assert "actions: read" in text
    assert "issues: write" not in text
    assert "pull-requests: write" not in text
    assert "contents: write" not in text

    # Diagnostic code must come from the repository's trusted default branch,
    # never from a failing revision or PR head. Checkout credentials also stay
    # disabled so later Python execution cannot inherit a persisted token.
    assert "ref: ${{ github.event.repository.default_branch }}" in text
    assert "persist-credentials: false" in text
    assert "workflow_run.head_sha" not in text
