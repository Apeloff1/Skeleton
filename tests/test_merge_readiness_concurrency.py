from pathlib import Path


def test_merge_readiness_cancels_superseded_prs_but_preserves_main_heads() -> None:
    workflow = Path(".github/workflows/merge-readiness.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert (
        "group: merge-readiness-${{ github.event.pull_request.number || github.sha }}"
        in workflow
    )
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in workflow
    assert "github.event.pull_request.number || github.ref" not in workflow
    assert "cancel-in-progress: true" not in workflow
    assert "preserving one canonical result for every main head SHA" in workflow
    assert "Secret/malware/provenance" in workflow
