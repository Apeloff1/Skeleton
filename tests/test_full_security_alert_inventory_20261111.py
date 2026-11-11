"""Regression: no accidental 50-alert truncation of canonical CodeQL backlog.

The inventory remains read-only with respect to security alerts. Its issue
digest exposes the exact extent of coverage rather than inventing closures.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "security-alert-inventory.yml"


def _source() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_inventory_is_large_enough_to_enumerate_all_151_codeql_alerts():
    source = _source()
    match = re.search(r"^\s+BATCH_SIZE:\s*'(\d+)'\s*$", source, re.MULTILINE)
    assert match is not None
    assert int(match.group(1)) >= 155  # 151 CodeQL + 4 dependency records
    assert "gh api --paginate --slurp" in source
    assert "/code-scanning/alerts?state=open&per_page=100" in source
    assert "/dependabot/alerts?state=open&per_page=100" in source
    assert "unique_by([.kind, .number])" in source


def test_digest_refuses_to_hide_partial_coverage_and_does_not_dismiss_alerts():
    source = _source()
    assert "actionable_total > BATCH_SIZE" in source
    assert 'coverage="partial:' in source
    assert "Detailed finding coverage:" in source
    assert "canonical_code_count" in source
    assert "code_count - archive_code_count" in source
    assert "Prioritized remediation batch:" in source
    assert "BODY_MAX_BYTES: '60000'" in source
    assert "body_bytes > BODY_MAX_BYTES" in source

    # This workflow inventories findings and edits its digest issue; it does
    # not manipulate any code-scanning or Dependabot security alert state.
    assert "gh api --method PATCH" not in source
    assert "gh api --method DELETE" not in source
    assert "gh api --method POST" not in source
    assert "gh issue edit" in source
    assert "gh issue reopen" in source
    assert "security-events: read" in source
    assert "vulnerability-alerts: read" in source
