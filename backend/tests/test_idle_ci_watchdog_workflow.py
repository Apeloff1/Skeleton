from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"


def _workflow(name: str) -> str:
    return (WORKFLOW_DIR / name).read_text(encoding="utf-8")


def test_watchdog_ledger_creation_uses_supported_gh_api_contract() -> None:
    text = _workflow("idle-ci-watchdog.yml")

    # `gh issue create` does not expose the generic `--json`/`--jq` output
    # flags. Keep creation on the REST endpoint so the numeric issue ID is
    # machine-readable and fail-closed before later mutation commands use it.
    assert "gh issue create" not in text
    assert "gh api \\" in text
    assert "--method POST" in text
    assert '"repos/${REPO}/issues"' in text
    assert "--jq '.number'" in text
    assert '[[ ! "$issue" =~ ^[0-9]+$ ]]' in text


def test_security_digest_creation_uses_supported_gh_api_contract() -> None:
    text = _workflow("idle-security-bot.yml")

    assert "gh issue create" not in text
    assert "gh api \\" in text
    assert "--method POST" in text
    assert '"repos/${REPO}/issues"' in text
    assert "-f 'labels[]=security'" in text
    assert "--jq '.number'" in text
    assert '[[ ! "$issue_number" =~ ^[0-9]+$ ]]' in text
