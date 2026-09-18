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


def test_security_digest_resolves_exact_issue_from_paginated_rest_results() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert '"/repos/${REPO}/issues?state=all&per_page=100"' in text
    assert '"/repos/${REPO}/issues?state=open&per_page=100"' not in text
    assert 'select((has("pull_request") | not) and (.title == $title))' in text
    assert "gh issue list" not in text
    assert "head -n 1" not in text


def test_security_digest_flattens_paginated_alert_pages() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert text.count("gh api --paginate --slurp") == 3
    assert "code-scanning/alerts?state=open&per_page=100" in text
    assert "dependabot/alerts?state=open&per_page=100" in text
    assert text.count("if type == \"array\" then .[] else empty end") == 3


def test_security_digest_remains_closed_after_refresh() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert 'repos/${REPO}/issues/${issue_number}' in text
    assert '-f state=closed' in text
