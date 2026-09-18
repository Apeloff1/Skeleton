from pathlib import Path


ROOT = Path('.github/workflows')


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding='utf-8')


def test_shift_supervisor_stops_mutating_under_actions_pressure() -> None:
    workflow = _read('shift-supervisor-control.yml')

    assert "MAX_QUEUED_ACTIONS_RUNS: '40'" in workflow
    assert 'id: pressure' in workflow
    assert '/actions/runs?status=queued&per_page=1' in workflow
    assert "echo 'proceed=false' >> \"$GITHUB_OUTPUT\"" in workflow
    assert "if: steps.pressure.outputs.proceed == 'true'" in workflow
    assert "Canonical-plan mutation: skipped" in workflow


def test_shift_supervisor_watchdog_does_not_redispatch_under_pressure() -> None:
    workflow = _read('shift-supervisor-watchdog.yml')

    assert "MAX_QUEUED_ACTIONS_RUNS: '40'" in workflow
    assert '/actions/runs?status=queued&per_page=1' in workflow
    assert "reason='actions-queue-pressure'" in workflow
    assert "if: steps.gate.outputs.dispatch == 'true'" in workflow
    assert 'gh workflow run "$SUPERVISOR_WORKFLOW"' in workflow


def test_idle_studio_uses_small_pressure_gate_before_mutation_job() -> None:
    workflow = _read('idle-studio.yml')

    assert '  pressure:' in workflow
    assert "MAX_QUEUED_ACTIONS_RUNS: '40'" in workflow
    assert '/actions/runs?status=queued&per_page=1' in workflow
    assert "echo 'proceed=false' >> \"$GITHUB_OUTPUT\"" in workflow
    assert '  studio:\n    needs: pressure' in workflow
    assert "needs.pressure.outputs.proceed == 'true'" in workflow
    assert "github.event.workflow_run.head_branch == 'main'" in workflow
    assert "github.event.workflow_run.conclusion == 'success'" in workflow
    assert 'Model calls, branch publication, and PR publication: skipped' in workflow


def test_pressure_guards_fail_closed_on_invalid_counts() -> None:
    for name in (
        'shift-supervisor-control.yml',
        'shift-supervisor-watchdog.yml',
        'idle-studio.yml',
    ):
        workflow = _read(name)
        assert 'queued_count' in workflow
        assert 'if ! [[ "$queued_count" =~ ^[0-9]+$ && "$threshold" =~ ^[0-9]+$ ]]; then' in workflow
        assert 'exit 1' in workflow
