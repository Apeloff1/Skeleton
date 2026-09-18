from pathlib import Path


WORKFLOW = Path(".github/workflows/actions-housekeeping-cli.yml")


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_live_reaper_is_bounded_to_obsolete_pr_runs() -> None:
    workflow = _workflow()

    assert "LIVE_RUN_STALE_MINUTES: '30'" in workflow
    assert "MAX_LIVE_CANCELS: '100'" in workflow
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
    assert "/force-cancel" not in workflow
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


def test_live_reaper_fails_closed_on_api_or_cancel_errors() -> None:
    workflow = _workflow()

    assert 'failed=$((failed + 1))' in workflow
    assert 'if (( failed > 0 )); then' in workflow
    assert 'exit 1' in workflow
    assert '[[ "$id" != "$GITHUB_RUN_ID" ]] || continue' in workflow
