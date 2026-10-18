from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ACTIVE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "idle-ci-watchdog.yml"
ARCHIVED_WORKFLOW = REPO_ROOT / ".github" / "workflows-archive" / "idle-ci-watchdog.yml"
# The retired watchdog remains subject to adversarial contract tests.
WORKFLOW = ACTIVE_WORKFLOW if ACTIVE_WORKFLOW.is_file() else ARCHIVED_WORKFLOW


def test_watchdog_ledger_creation_uses_supported_gh_api_contract() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    # `gh issue create` does not expose the generic `--json`/`--jq` output
    # contract used by the watchdog. Keep creation on the issues REST endpoint,
    # require a machine-readable issue number, and fail closed before retries.
    assert "gh issue create" not in text
    assert "gh api" in text
    assert "--method POST" in text
    assert '"repos/${REPO}/issues"' in text
    assert "--jq '.number'" in text
    assert '[[ ! "$issue" =~ ^[0-9]+$ ]]' in text


def test_watchdog_only_marks_a_run_after_rerun_started() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    # The GitHub run object is the authoritative once-only guard. A failed
    # rerun API call must not poison the issue ledger and suppress a later pass.
    assert '"repos/${REPO}/actions/runs/${id}"' in text
    assert "--jq '.run_attempt'" in text
    assert '(( run_attempt > 1 ))' in text

    rerun = text.index('if gh run rerun "$id" --repo "$REPO"; then')
    success_marker = text.index('run:${id}', rerun)
    assert success_marker > rerun
    assert "could not rerun transient timed_out candidate:${id}" in text


def test_watchdog_parses_each_run_as_a_json_record() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    # Bash treats tab as IFS whitespace and collapses empty TSV fields. GitHub
    # legitimately returns null/empty values for live runs, so positional TSV
    # parsing can shift createdAt into the URL column and make `date` fail.
    # Keep record boundaries in JSON and extract fields by name instead.
    assert "@tsv" not in text
    assert "while IFS= read -r run; do" in text
    assert "done < <(jq -c '.[]'" in text
    assert "id=$(jq -r '.databaseId // empty'" in text
    assert "status=$(jq -r '.status // empty'" in text
    assert "conclusion=$(jq -r '.conclusion // \"none\"'" in text
    assert "created=$(jq -r '.createdAt // empty'" in text
    assert "url=$(jq -r '.url // empty'" in text
    assert '[[ -n "$id" && -n "$created" ]] || continue' in text


def test_watchdog_reuses_and_keeps_machine_ledger_closed() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert '--state all --search "${ISSUE_TITLE} in:title"' in text
    assert '--json number,title' in text
    assert 'jq -r --arg title "$ISSUE_TITLE"' in text
    assert "select(.title == $title)" in text
    assert 'repos/${REPO}/issues/${issue}' in text
    assert '-f state=closed' in text


def test_watchdog_does_not_resurrect_cancelled_pr_generations() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "[[ \"$conclusion\" == 'timed_out' ]] || continue" in text
    assert "[[ \"$conclusion\" == 'cancelled' ||" not in text
    assert "Only successful" in text or "Only successful" in text.lower()


def test_watchdog_does_not_send_issue_alerts_for_failed_retry_attempts() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    retries = text.split('if gh run rerun "$id" --repo "$REPO"; then', 1)[1]
    assert 'gh issue comment "$issue" --repo "$REPO" --body "CI watchdog retrying' in retries
    failed = retries.split("else", 1)[1].split("fi", 1)[0]
    assert "gh issue comment" not in failed
    assert "echo \"::warning::CI watchdog could not rerun" in failed
