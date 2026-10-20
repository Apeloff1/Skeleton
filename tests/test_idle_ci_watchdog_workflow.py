from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / ".github/workflows/idle-ci-watchdog.yml"
ARCHIVED = ROOT / ".github/workflows-archive/idle-ci-watchdog.yml"
WORKFLOW = ACTIVE if ACTIVE.is_file() else ARCHIVED


def test_watchdog_preserves_in_progress_run_identity_without_tsv_collapsing() -> None:
    """Optional conclusions must not shift the record columns."""
    assert WORKFLOW.is_file()
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "@tsv" not in workflow
    assert "while IFS= read -r run; do" in workflow
    assert "done < <(jq -c '.[]'" in workflow
    assert "conclusion=$(jq -r '.conclusion // \\"none\\"'" in workflow
    assert "created=$(jq -r '.createdAt // empty'" in workflow
    assert "url=$(jq -r '.url // empty'" in workflow
