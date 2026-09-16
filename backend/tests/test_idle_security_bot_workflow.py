from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "idle-security-bot.yml"


def test_security_digest_uses_supported_issue_creation_contract() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "gh issue create" not in text
    assert 'gh api --method POST "repos/${REPO}/issues"' in text
    assert "--jq '.number'" in text
    assert '[[ ! "$issue_number" =~ ^[0-9]+$ ]]' in text
    assert "select(.title == $title)" in text


def test_security_digest_flattens_paginated_alert_pages() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert text.count("gh api --paginate --slurp") == 2
    assert "code-scanning/alerts?state=open&per_page=100" in text
    assert "dependabot/alerts?state=open&per_page=100" in text
    assert text.count("if type == \"array\" then .[] else empty end") == 2
