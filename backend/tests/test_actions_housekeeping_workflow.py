from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "actions-housekeeping-cli.yml"


def test_unsuccessful_run_cleanup_queries_stale_runs_directly() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert 'cutoff_iso=$(date -u -d "${FAILED_RUN_RETENTION_DAYS} days ago" +%Y-%m-%dT%H:%M:%SZ)' in text
    assert '--created "<${cutoff_iso}"' in text
    assert '--limit "$MAX_RUN_DELETES"' in text
    assert '--limit 1000 --status "$status_name"' not in text


def test_unsuccessful_run_cleanup_keeps_local_age_and_global_cap_guards() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert 'created_epoch=$(date -u -d "$created" +%s)' in text
    assert "created_epoch >= cutoff || deleted >= MAX_RUN_DELETES" in text
    assert "sort -t $'\\t' -k2,2 -k1,1n -u" in text
    assert '[[ "$id" != "$GITHUB_RUN_ID" ]]' in text
