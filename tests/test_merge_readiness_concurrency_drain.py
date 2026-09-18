from pathlib import Path
import re

WORKFLOW = Path(".github/workflows/merge-readiness-concurrency-drain.yml")
CURRENT_MAIN_SHA = "7572a9dd3a0c4658e0425d5e379cbb9c5bd653b7"


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
    assert len(shas) == 13
    assert len(set(shas)) == 13
    assert CURRENT_MAIN_SHA not in shas


def test_tombstone_runtime_rejects_current_or_malformed_identity() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert '[[ "$LEGACY_SHA" =~ ^[0-9a-f]{40}$ ]]' in workflow
    assert '[[ "$CURRENT_MAIN_SHA" =~ ^[0-9a-f]{40}$ ]]' in workflow
    assert '[[ "$LEGACY_SHA" != "$CURRENT_MAIN_SHA" ]]' in workflow
