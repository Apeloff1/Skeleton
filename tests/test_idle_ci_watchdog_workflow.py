from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / ".github/workflows/idle-ci-watchdog.yml"
ARCHIVE = ROOT / ".github/workflows-archive/idle-ci-watchdog.yml"
WORKFLOW = ACTIVE if ACTIVE.is_file() else ARCHIVE


def test_watchdog_preserves_columns_for_in_progress_runs() -> None:
    """Null conclusions must not collapse the tab-delimited read fields."""
    workflow = WORKFLOW.read_text(encoding="utf-8")

    # Parsed JSON records preserve column identity even when conclusion is
    # null. Old whitespace-collapsing tab parsing is no longer authoritative.
    assert WORKFLOW.is_file()
    assert "jq -c '.[]'" in workflow
    assert '(.conclusion // "none")' not in workflow
    assert "conclusion=$(jq -r '.conclusion // \"none\"'" in workflow
