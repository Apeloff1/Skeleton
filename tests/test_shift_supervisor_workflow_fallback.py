from pathlib import Path


WORKFLOW = Path(".github/workflows/shift-supervisor-control.yml")


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_supervisor_keeps_cron_and_adds_main_push_fallback():
    workflow = _workflow_text()

    assert "- cron: '2,32 * * * *'" in workflow
    assert "- cron: '17,47 * * * *'" in workflow
    assert "workflow_dispatch:" in workflow
    assert "push:\n    branches: [main]" in workflow
    assert "pull_request:" not in workflow


def test_main_push_fallback_is_bounded_by_plan_freshness():
    workflow = _workflow_text()

    assert "PLAN_FRESHNESS_SECONDS: '1200'" in workflow
    assert "if [[ \"$EVENT_NAME\" == 'push' ]]" in workflow
    assert "age_seconds >= 0 && age_seconds < PLAN_FRESHNESS_SECONDS" in workflow
    assert "echo \"run=$should_run\" >> \"$GITHUB_OUTPUT\"" in workflow
    assert workflow.index("Gate main-push fallback on stale or missing canonical plan") < workflow.index(
        "Checkout trusted main"
    )


def test_push_fallback_uses_trusted_main_and_runs_both_plan_producers():
    workflow = _workflow_text()

    assert "ref: main" in workflow
    assert "persist-credentials: false" in workflow
    assert "steps.fallback.outputs.run == 'true'" in workflow
    assert (
        "\"$EVENT_NAME\" == 'workflow_dispatch' || \"$EVENT_NAME\" == 'push' || "
        "\"$EVENT_SCHEDULE\" == '2,32 * * * *'"
    ) in workflow
    assert "role='both'" in workflow


def test_fallback_does_not_broaden_supervisor_permissions():
    workflow = _workflow_text()

    assert "permissions: {}" in workflow
    assert "actions: read" in workflow
    assert "contents: read" in workflow
    assert "issues: write" in workflow
    assert "pull-requests: read" in workflow
    assert "security-events: read" in workflow
    assert "contents: write" not in workflow
    assert "actions: write" not in workflow
    assert "pull-requests: write" not in workflow


def test_github_automation_uses_bounded_run_once_not_run_forever():
    workflow = _workflow_text()

    assert "python -m core.shift_supervisor" in workflow
    assert "--once" in workflow
    assert "--role" in workflow
    assert "--state-in" in workflow
    assert "--state-out" in workflow
    assert "run_forever" not in workflow
    assert "python -m core.shift_supervisor \\\n            --once" in workflow
