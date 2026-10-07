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


def test_live_reaper_can_normally_cancel_proven_stale_security_pr_runs() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "LIVE_RUN_STALE_MINUTES: '10'" in text
    assert "security_pr_candidate=false" in text
    assert "security_pr_candidate=true" in text

    event_gate = text.index('case "$event" in')
    stale_proof = text.index('obsolete=true', event_gate)
    ordinary_cancel = text.index('/actions/runs/${id}/cancel', stale_proof)
    security_force_guard = text.index(
        'if [[ "$security_pr_candidate" == "true" ]]; then',
        ordinary_cancel,
    )
    force_cancel = text.index('/actions/runs/${id}/force-cancel', security_force_guard)

    assert event_gate < stale_proof < ordinary_cancel < security_force_guard < force_cancel
    assert "security PR preserve after ordinary cancel failure" in text


def test_live_reaper_preserves_non_pr_security_runs_and_never_force_escalates_them() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    event_gate = text.index('case "$event" in')
    event_block = text[event_gate:text.index('run_json=', event_gate)]
    assert 'if [[ "$security_pr_candidate" == "true" ]]; then' in event_block
    assert 'kept_security=$((kept_security + 1))' in event_block

    assert (
        "Security/provenance/artifact/dependency PR runs are never "
        "force-cancelled after an ordinary cancellation failure."
    ) in text
