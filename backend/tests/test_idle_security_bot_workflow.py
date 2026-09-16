from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "idle-security-bot.yml"


def test_idle_security_digest_creation_uses_supported_gh_api_contract() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    # `gh issue create` does not expose generic `--json`/`--jq` output flags.
    # Create through the REST endpoint so the issue number remains
    # machine-readable and validate it before later summary bookkeeping.
    assert 'issue_number=$(gh issue create' not in text
    assert 'gh api --method POST "repos/${REPO}/issues"' in text
    assert '-f title="$ISSUE_TITLE"' in text
    assert '-F body=@"$body_file"' in text
    assert "-f 'labels[]=security'" in text
    assert "--jq '.number'" in text
    assert '[[ ! "$issue_number" =~ ^[0-9]+$ ]]' in text


def test_idle_security_digest_remains_inventory_only() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert 'security-events: read' in text
    assert 'vulnerability-alerts: read' in text
    assert 'issues: write' in text
    assert 'No alerts were dismissed or modified.' in text
