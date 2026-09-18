from pathlib import Path
import re

WORKFLOW = Path(".github/workflows/merge-readiness-concurrency-drain.yml")
CURRENT_MAIN_SHA = "1344c3bf3c9fa1cf3b33a02236037a9d3a8e718e"


def test_legacy_merge_readiness_tombstones_are_bounded_and_read_only() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "permissions: {}" in workflow
    assert "group: merge-readiness-${{ matrix.sha }}" in workflow
    assert "cancel-in-progress: true" in workflow
    assert "runs-on: ubuntu-24.04-arm" in workflow
    assert "timeout-minutes: 2" in workflow
    assert "workflow_dispatch:" in workflow
    assert "paths:" in workflow
    assert "merge-readiness-concurrency-drain.yml" in workflow

    shas = re.findall(r"^          - ([0-9a-f]{40})$", workflow, flags=re.MULTILINE)
    assert len(shas) == 6
    assert len(set(shas)) == 6
    assert CURRENT_MAIN_SHA not in shas


def test_tombstone_runtime_rejects_current_or_malformed_identity() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert '[[ "$LEGACY_SHA" =~ ^[0-9a-f]{40}$ ]]' in workflow
    assert '[[ "$CURRENT_MAIN_SHA" =~ ^[0-9a-f]{40}$ ]]' in workflow
    assert '[[ "$LEGACY_SHA" != "$CURRENT_MAIN_SHA" ]]' in workflow
