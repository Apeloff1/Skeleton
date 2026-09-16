from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "idle-ci-watchdog.yml"


def test_watchdog_ledger_creation_uses_supported_gh_api_contract() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    # `gh issue create` does not expose the generic `--json`/`--jq` output
    # flags. Keep creation on the REST endpoint so the numeric issue ID is
    # machine-readable and fail-closed before later mutation commands use it.
    assert "gh issue create" not in text
    assert "gh api \\\n              --method POST" in text
    assert '"repos/${REPO}/issues"' in text
    assert "--jq '.number'" in text
    assert '[[ ! "$issue" =~ ^[0-9]+$ ]]' in text
