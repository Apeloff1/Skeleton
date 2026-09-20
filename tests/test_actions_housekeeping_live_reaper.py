from pathlib import Path


WORKFLOW = Path(".github/workflows/actions-housekeeping-cli.yml")


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_live_reaper_is_bounded_to_obsolete_pr_runs() -> None:
    workflow = _workflow()

    assert "LIVE_RUN_STALE_MINUTES: '30'" in workflow
    assert "LIVE_FORCE_CANCEL_STALE_MINUTES: '1440'" in workflow
    assert "FORCE_CANCEL_ATTEMPTS: '2'" in workflow
    assert "FORCE_CANCEL_REJECT_BACKOFF_SECONDS: '1'" in workflow
    assert "FORCE_CANCEL_POLL_SECONDS: '2'" in workflow
    assert "MAX_LIVE_CANCELS: '100'" in workflow
    assert "pull-requests: read" in workflow
    assert "pull-requests: write" not in workflow
    assert "for status_name in queued in_progress waiting pending requested" in workflow
    assert "pull_request) ;;" in workflow
    assert "pull_request_target" not in workflow
    assert ".pull_requests[]?.number" in workflow
    assert '"/repos/${REPO}/pulls/${pr_number}"' in workflow
    assert "pr_state=$(jq -r '.state // empty'" in workflow
    assert "pr_head_sha=$(jq -r '.head.sha // empty'" in workflow
    assert "pr_head_repo=$(jq -r '.head.repo.full_name // empty'" in workflow
    assert 'if [[ "$pr_state" == "open" && "$pr_head_sha" == "$head_sha" ]]' in workflow
    assert 'if [[ "$pr_head_repo" != "$REPO" || "$pr_head_ref" != "$head_branch" ]]' in workflow
    assert '--method POST "/repos/${REPO}/actions/runs/${id}/cancel"' in workflow
    assert '--method POST "/repos/${REPO}/actions/runs/${id}/force-cancel"' in workflow
    assert "recover_pr_numbers()" in workflow
    assert "pr_contains_sha()" in workflow
    assert "/pulls/${pr_number}/commits?per_page=100&page=${page}" in workflow
    assert '-f "head=${owner}:${head_branch}"' in workflow
    assert "for page in $(seq 1 10)" in workflow


def test_live_reaper_preserves_security_and_unlinked_runs() -> None:
    workflow = _workflow()

    for protected_name in (
        "*Malware*",
        "*Secret*",
        "*Security*",
        "*CodeQL*",
        "*Provenance*",
        "*Artifact\\ Policy*",
        "*Dependency*",
        "*Repository\\ Hygiene*",
        "*Workflow\\ Input\\ Security*",
    ):
        assert protected_name in workflow

    assert 'kept_security=$((kept_security + 1))' in workflow
    assert 'kept_unlinked=$((kept_unlinked + 1))' in workflow
    assert 'case "$event" in' in workflow
    assert 'pull_request) ;;' in workflow


def test_live_reaper_preserves_ambiguous_targets_without_aborting_housekeeping() -> None:
    workflow = _workflow()

    live_reaper = workflow.split(
        "      - name: Cancel obsolete live PR runs\n", 1
    )[1].split(
        "      - name: Prune only cold Actions caches\n", 1
    )[0]

    assert 'preserved_errors=$((preserved_errors + 1))' in live_reaper
    assert 'if (( preserved_errors > 0 )); then' in live_reaper
    assert '::warning::Live-run reaper preserved' in live_reaper
    assert 'exit 1' not in live_reaper
    assert '[[ "$id" != "$GITHUB_RUN_ID" ]] || continue' in live_reaper
    assert '[[ ! "$head_sha" =~ ^[0-9a-fA-F]{40}$ ]]' in live_reaper
    assert "return \"$status\"" in live_reaper


def test_housekeeping_drain_uses_independent_arm_recovery_lane() -> None:
    workflow = _workflow()

    assert "runs-on: ubuntu-24.04-arm" in workflow
    assert "group: actions-housekeeping-cli-v2-${{ github.repository }}" in workflow
    assert "cancel-in-progress: false" in workflow


def test_live_reaper_force_cancel_is_queued_only_old_and_revalidated() -> None:
    workflow = _workflow()
    live_reaper = workflow.split(
        "      - name: Cancel obsolete live PR runs\n", 1
    )[1].split(
        "      - name: Prune only cold Actions caches\n", 1
    )[0]

    ordinary = live_reaper.index(
        '--method POST "/repos/${REPO}/actions/runs/${id}/cancel"'
    )
    force = live_reaper.index(
        '--method POST "/repos/${REPO}/actions/runs/${id}/force-cancel"'
    )
    assert ordinary < force
    assert 'force_cutoff=$(date -u -d "${LIVE_FORCE_CANCEL_STALE_MINUTES} minutes ago" +%s)' in live_reaper
    assert 'if [[ "$status_now" != "queued" || "$created_epoch" -ge "$force_cutoff" ]]; then' in live_reaper
    assert 'force_obsolete=true' in live_reaper
    assert 'if [[ "$force_pr_state" == "open" && "$force_pr_head_sha" == "$head_sha" ]]' in live_reaper
    assert 'if [[ "$force_status" != "queued" || "$force_sha" != "$head_sha" || "$force_branch" != "$head_branch" || "$force_event" != "pull_request" ]]' in live_reaper
    assert 'forced=$((forced + 1))' in live_reaper
    assert 'cancelled + forced >= MAX_LIVE_CANCELS' in live_reaper


def test_live_reaper_retries_force_cancel_with_fresh_identity_and_polling() -> None:
    workflow = _workflow()
    live_reaper = workflow.split(
        "      - name: Cancel obsolete live PR runs\n", 1
    )[1].split(
        "      - name: Prune only cold Actions caches\n", 1
    )[0]

    assert 'for force_attempt in $(seq 1 "$FORCE_CANCEL_ATTEMPTS"); do' in live_reaper
    assert 'force-pr-${id}-${force_attempt}-${pr_number}.json' in live_reaper
    assert 'force-run-${id}-${force_attempt}.json' in live_reaper
    assert 'force-cancel rejected: run=${id} attempt=${force_attempt}; skipping completion polls' in live_reaper
    assert 'sleep "$FORCE_CANCEL_REJECT_BACKOFF_SECONDS"' in live_reaper
    rejected = live_reaper.index(
        'force-cancel rejected: run=${id} attempt=${force_attempt}; skipping completion polls'
    )
    polling = live_reaper.index('for force_poll in 1 2 3; do')
    assert 'continue' in live_reaper[rejected:polling]
    assert 'sleep "$FORCE_CANCEL_POLL_SECONDS"' in live_reaper[polling:]
    assert 'force-cancel accepted: run=${id} attempt=${force_attempt}' in live_reaper
    assert 'force-cancel stuck: run=${id} remained queued after ${FORCE_CANCEL_ATTEMPTS}' in live_reaper
    assert 'force_stuck=$((force_stuck + 1))' in live_reaper
    assert 'force_transitioned=$((force_transitioned + 1))' in live_reaper
    assert '--method DELETE "/repos/${REPO}/actions/runs/${id}"' not in live_reaper
