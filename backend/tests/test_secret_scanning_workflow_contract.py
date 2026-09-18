from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "secret-scanning.yml"


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _push_case(text: str) -> str:
    marker = "            push)\n"
    assert marker in text
    remainder = text.split(marker, 1)[1]
    return remainder.split("              ;;\n", 1)[0]


def test_new_branch_push_is_bounded_to_default_branch_merge_base() -> None:
    text = _workflow_text()
    push_case = _push_case(text)

    assert "DEFAULT_BRANCH: ${{ github.event.repository.default_branch }}" in text
    assert 'baseline_ref="refs/remotes/origin/${DEFAULT_BRANCH}"' in push_case
    assert 'git rev-parse --verify --quiet "${baseline_ref}^{commit}"' in push_case
    assert 'merge_base="$(git merge-base "$CURRENT_SHA" "$baseline_sha")"' in push_case
    assert 'scan_range="${merge_base}..${CURRENT_SHA}"' in push_case

    # A lone head SHA passed to Gitleaks means "walk all reachable history".
    # That is correct for explicit workflow_dispatch, but never for a branch-
    # creation push where github.event.before is the all-zero sentinel.
    assert 'scan_range="$CURRENT_SHA"' not in push_case


def test_new_branch_without_unique_commits_is_an_explicit_noop() -> None:
    text = _workflow_text()
    push_case = _push_case(text)

    assert 'if [[ "$merge_base" == "$CURRENT_SHA" ]]; then' in push_case
    assert "has_commits=false" in push_case
    assert "printf 'has_commits=%s\\n' \"$has_commits\" >> \"$GITHUB_OUTPUT\"" in text
    assert "if: steps.scan-range.outputs.has_commits == 'false'" in text
    assert "if: steps.scan-range.outputs.has_commits == 'true'" in text


def test_new_branch_baseline_resolution_fails_closed() -> None:
    push_case = _push_case(_workflow_text())

    assert '[[ -n "$DEFAULT_BRANCH" ]] || {' in push_case
    assert "Unable to resolve default-branch baseline for branch secret scan" in push_case
    assert "Invalid default-branch baseline for branch secret scan" in push_case
    assert "Unable to resolve merge base for branch secret scan" in push_case
    assert "Invalid merge base for branch secret scan" in push_case


def test_default_branch_push_and_pull_request_ranges_remain_incremental() -> None:
    text = _workflow_text()

    assert 'scan_range="${PR_BASE_SHA}..${PR_HEAD_SHA}"' in text
    assert 'scan_range="${PUSH_BEFORE_SHA}..${CURRENT_SHA}"' in text


def test_feature_pushes_are_branch_cumulative_and_safely_supersedable() -> None:
    text = _workflow_text()
    push_case = _push_case(text)

    assert "REF_NAME: ${{ github.ref_name }}" in text
    assert '"$REF_NAME" != "$DEFAULT_BRANCH"' in push_case
    assert 'scan_range="${merge_base}..${CURRENT_SHA}"' in push_case
    assert (
        "github.event_name == 'push' && "
        "github.ref_name != github.event.repository.default_branch && github.ref_name"
    ) in text
    assert (
        "github.event_name == 'push' && "
        "github.ref_name != github.event.repository.default_branch"
    ) in text


def test_default_branch_pushes_remain_sha_keyed_and_non_preemptive() -> None:
    text = _workflow_text()

    assert "|| github.sha }}" in text
    assert (
        "cancel-in-progress: ${{ github.event_name == 'pull_request' || "
        "(github.event_name == 'push' && "
        "github.ref_name != github.event.repository.default_branch) }}"
    ) in text
