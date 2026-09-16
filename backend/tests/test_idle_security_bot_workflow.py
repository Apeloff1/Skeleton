from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "idle-security-bot.yml"


def test_security_digest_creation_uses_supported_gh_api_contract() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    # `gh issue create` does not expose the generic `--json`/`--jq` output
    # contract. Keep first-time digest creation on the issues REST endpoint so
    # the returned issue number is machine-readable and validated before use.
    assert "gh issue create" not in text
    assert "gh api \\" in text
    assert "--method POST" in text
    assert '"repos/${REPO}/issues"' in text
    assert '-f body="$(cat "$body_file")"' in text
    assert "-f 'labels[]=security'" in text
    assert "--jq '.number'" in text
    assert '[[ ! "$issue_number" =~ ^[0-9]+$ ]]' in text
