from pathlib import Path


def test_merge_readiness_collapses_superseded_pr_and_main_runs() -> None:
    workflow = Path(".github/workflows/merge-readiness.yml").read_text(encoding="utf-8")

    assert (
        "group: merge-readiness-${{ github.event.pull_request.number || github.ref }}"
        in workflow
    )
    assert "cancel-in-progress: true" in workflow
    assert "github.event.pull_request.number || github.sha" not in workflow
    assert "current integration state" in workflow
    assert "Secret/malware/provenance" in workflow
