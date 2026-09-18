from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / '.github' / 'workflows' / 'secret-scanning.yml'


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding='utf-8')


def _push_case(text: str) -> str:
    marker = '            push)\n'
    assert marker in text
    remainder = text.split(marker, 1)[1]
    return remainder.split('              ;;\n', 1)[0]


def test_branch_push_is_bounded_to_default_branch_merge_base() -> None:
    text = _workflow_text()
    push_case = _push_case(text)

    assert 'DEFAULT_BRANCH: ${{ github.event.repository.default_branch }}' in text
    assert 'REF_NAME: ${{ github.ref_name }}' in text
    assert 'baseline_ref="refs/remotes/origin/${DEFAULT_BRANCH}"' in push_case
    assert 'git rev-parse --verify --quiet "${baseline_ref}^{commit}"' in push_case
    assert 'merge_base="$(git merge-base "$CURRENT_SHA" "$baseline_sha")"' in push_case
    assert 'scan_range="${merge_base}..${CURRENT_SHA}"' in push_case


def test_branch_without_unique_commits_is_an_explicit_noop() -> None:
    text = _workflow_text()
    push_case = _push_case(text)

    assert 'if [[ "$merge_base" == "$CURRENT_SHA" ]]; then' in push_case
    assert 'has_commits=false' in push_case
    assert "if: steps.scan-range.outputs.has_commits == 'false'" in text
    assert "if: steps.scan-range.outputs.has_commits == 'true'" in text


def test_branch_baseline_resolution_fails_closed() -> None:
    push_case = _push_case(_workflow_text())

    assert '[[ -n "$DEFAULT_BRANCH" ]] || {' in push_case
    assert 'Unable to resolve default-branch baseline for branch secret scan' in push_case
    assert 'Invalid default-branch baseline for branch secret scan' in push_case
    assert 'Unable to resolve merge base for branch secret scan' in push_case
    assert 'Invalid merge base for branch secret scan' in push_case


def test_pull_request_range_remains_incremental() -> None:
    text = _workflow_text()

    assert 'scan_range="${PR_BASE_SHA}..${PR_HEAD_SHA}"' in text


def test_main_push_is_cumulative_from_last_successful_ancestor() -> None:
    push_case = _push_case(_workflow_text())

    assert 'actions/workflows/secret-scanning.yml/runs?branch=${DEFAULT_BRANCH}&status=success&per_page=100' in push_case
    assert 'git merge-base --is-ancestor "$candidate" "$CURRENT_SHA"' in push_case
    assert 'success_base="$candidate"' in push_case
    assert 'scan_range="${success_base}..${CURRENT_SHA}"' in push_case
    assert 'scan_range="${PUSH_BEFORE_SHA}..${CURRENT_SHA}"' not in push_case


def test_main_push_history_lookup_fails_closed_to_full_history() -> None:
    push_case = _push_case(_workflow_text())

    assert 'Unable to load successful main Secret scanning history' in push_case
    assert 'Invalid successful Secret scanning head SHA' in push_case
    assert 'No successful ancestor Secret scanning baseline' in push_case
    assert 'scan_range="$CURRENT_SHA"' in push_case


def test_push_concurrency_is_branch_coalesced_with_read_only_actions_history() -> None:
    text = _workflow_text()

    assert 'actions: read' in text
    assert 'GH_TOKEN: ${{ github.token }}' in text
    assert "group: secret-scanning-${{ github.event.pull_request.number || (github.event_name == 'push' && github.ref_name) || github.sha }}" in text
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' || github.event_name == 'push' }}" in text


def test_workflow_dispatch_keeps_explicit_full_history_semantics() -> None:
    text = _workflow_text()

    assert 'workflow_dispatch)' in text
    assert 'scan_range="$CURRENT_SHA"' in text
