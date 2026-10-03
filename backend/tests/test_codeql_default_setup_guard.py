from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "codeql-default-setup-repair.yml"


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_codeql_guard_treats_known_integration_read_403_as_nonfatal() -> None:
    text = _workflow_text()

    assert (
        'if current="$(gh api "repos/${GH_REPO}/code-scanning/default-setup" '
        '2>"${api_error_file}")"; then'
    ) in text
    assert "HTTP 403|Resource not accessible by integration" in text
    assert "the guard will not create a red CI loop for this expected 403" in text

    known_boundary = text.index("HTTP 403|Resource not accessible by integration")
    unexpected_boundary = text.index(
        "Unable to read CodeQL default setup from GitHub API for an unexpected reason."
    )
    expected_block = text[known_boundary:unexpected_boundary]
    assert "exit 0" in expected_block


def test_codeql_guard_keeps_unknown_api_failures_fail_closed() -> None:
    text = _workflow_text()

    unexpected = (
        'echo "::error::Unable to read CodeQL default setup from GitHub API '
        'for an unexpected reason."\n'
        "            exit 1"
    )
    assert unexpected in text


def test_codeql_guard_does_not_claim_configuration_when_read_is_denied() -> None:
    text = _workflow_text()

    denied_block_start = text.index(
        "CodeQL default-setup state is not readable by this integration"
    )
    denied_block_end = text.index(
        "Unable to read CodeQL default setup from GitHub API for an unexpected reason."
    )
    denied_block = text[denied_block_start:denied_block_end]

    assert "Maintained-language coverage is configured" not in denied_block
    assert "issue #${TRACKING_ISSUE} remains the admin boundary" in denied_block
