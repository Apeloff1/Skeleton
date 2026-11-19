from pathlib import Path


WORKFLOW = Path(".github/workflows/idle-ci-watchdog.yml")


def test_watchdog_preserves_columns_for_in_progress_runs() -> None:
    """Null conclusions must not collapse the tab-delimited read fields."""
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert '(.conclusion // "none")' in workflow
    assert "[.databaseId,.name,.status,(.conclusion // \"none\"),.createdAt,.url] | @tsv" in workflow
