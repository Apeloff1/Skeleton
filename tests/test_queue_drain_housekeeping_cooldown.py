from pathlib import Path


WORKFLOW = Path(".github/workflows/queue-drain.yml")


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_housekeeping_wake_has_success_only_cooldown() -> None:
    workflow = _workflow()

    assert "HOUSEKEEPING_RECENT_SUCCESS_COOLDOWN_MINUTES: '360'" in workflow
    assert (
        "/actions/workflows/${HOUSEKEEPING_WORKFLOW}/runs?"
        "status=completed&per_page=20"
    ) in workflow
    assert "recent_success=$(gh api" in workflow
    assert 'select(.conclusion == "success")' in workflow
    assert (
        'cooldown_cutoff=$(date -u -d '
        '"${HOUSEKEEPING_RECENT_SUCCESS_COOLDOWN_MINUTES} minutes ago" +%s)'
    ) in workflow
    assert "recent_epoch >= cooldown_cutoff" in workflow
    assert "successful Housekeeping run is inside" in workflow


def test_housekeeping_wake_still_dispatches_after_cooldown() -> None:
    workflow = _workflow()
    wake = workflow.split("  wake-housekeeping:\n", 1)[1]

    cooldown_guard = wake.index("recent_epoch >= cooldown_cutoff")
    dispatch = wake.index(
        'gh workflow run "$HOUSEKEEPING_WORKFLOW" --repo "$REPO" --ref main'
    )
    assert cooldown_guard < dispatch
    assert "existing Housekeeping run is ${housekeeping_status}" in wake
    assert "Old queued candidate observed: ${stale_candidate}" in wake


def test_housekeeping_wake_keeps_identity_revalidation_boundary() -> None:
    workflow = _workflow()
    wake = workflow.split("  wake-housekeeping:\n", 1)[1]

    assert "Safety: dispatch only; Housekeeping independently re-proves PR/run identity" in wake
    assert "HOUSEKEEPING_WAKE_STALE_MINUTES: '1440'" in wake
    assert "actions: write" in wake
