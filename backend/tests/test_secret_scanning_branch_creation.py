from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "secret-scanning.yml"
)
ZERO_BEFORE = (
    'if [[ "$PUSH_BEFORE_SHA" == '
    '"0000000000000000000000000000000000000000" ]]; then'
)


def _branch_creation_block() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert ZERO_BEFORE in text
    return text.split(ZERO_BEFORE, 1)[1].split("\n              else\n", 1)[0]


def test_branch_creation_secret_scan_is_bounded_to_default_branch_delta() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    block = _branch_creation_block()

    assert "fetch-depth: 0" in text
    assert "DEFAULT_BRANCH: ${{ github.event.repository.default_branch }}" in text
    assert 'default_ref="refs/remotes/origin/${DEFAULT_BRANCH}"' in block
    assert 'git rev-parse --verify "${default_ref}^{commit}"' in block
    assert 'git merge-base "$CURRENT_SHA" "$default_sha"' in block
    assert 'scan_range="${merge_base}..${CURRENT_SHA}"' in block
    assert 'scan_range="$CURRENT_SHA"' not in block


def test_branch_creation_secret_scan_fails_closed_without_trusted_ancestry() -> None:
    block = _branch_creation_block()

    assert "Default branch is unavailable for branch-creation scan" in block
    assert "Default branch commit is unavailable for branch-creation scan" in block
    assert "Branch-creation head has no trusted default-branch merge base" in block
    assert "Invalid merge base for branch-creation scan" in block
