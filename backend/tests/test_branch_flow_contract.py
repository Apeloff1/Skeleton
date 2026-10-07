from __future__ import annotations

from pathlib import Path

from scripts.check_branch_flow_contract import violations_for_text

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "branch-flow.yml"


def _source() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _replace_once(source: str, old: str, new: str) -> str:
    assert old in source, f"fixture marker missing: {old!r}"
    return source.replace(old, new, 1)


def _messages(source: str) -> str:
    return "\n".join(violations_for_text(source))


def test_live_branch_flow_contract_passes() -> None:
    assert violations_for_text(_source()) == []


def test_rejects_pull_request_trigger() -> None:
    source = _replace_once(
        _source(),
        "  workflow_dispatch:\n",
        "  workflow_dispatch:\n  pull_request:\n    types: [synchronize]\n",
    )
    assert "must never run on pull-request events" in _messages(source)


def test_rejects_main_push_trigger() -> None:
    source = _replace_once(
        _source(),
        "  workflow_dispatch:\n",
        "  workflow_dispatch:\n  push:\n    branches: [main]\n",
    )
    assert "must not run on every main push" in _messages(source)


def test_rejects_async_update_branch_endpoint() -> None:
    source = _replace_once(_source(), "f'/repos/{repo}/merges'", "f'/repos/{repo}/pulls/{number}/update-branch'")
    assert "asynchronous update-branch endpoint is forbidden" in _messages(source)


def test_rejects_broader_write_permission() -> None:
    source = _replace_once(_source(), "      pull-requests: read\n", "      pull-requests: write\n")
    assert "exactly one write scope: contents: write" in _messages(source)


def test_rejects_loss_of_head_settle_window() -> None:
    source = _replace_once(_source(), "          min_head_age_seconds = 180", "          min_head_age_seconds = 0")
    assert "180-second head settle window" in _messages(source)


def test_rejects_loss_of_fresh_head_revalidation() -> None:
    source = _replace_once(
        _source(),
        "                      fresh_head.get('sha') != expected_head or\n",
        "",
    )
    assert "revalidate the head SHA" in _messages(source)


def test_rejects_loss_of_workflow_file_filter() -> None:
    source = _replace_once(
        _source(),
        "          def touches_workflows(number, expected_files):",
        "          def touches_other_files(number, expected_files):",
    )
    assert "complete changed-file set" in _messages(source)


def test_rejects_loss_of_workflow_rename_detection() -> None:
    source = _replace_once(
        _source(),
        "for field in ('filename', 'previous_filename')",
        "for field in ('filename',)",
    )
    assert "both sides of a rename" in _messages(source)


def test_rejects_incomplete_workflow_file_enumeration() -> None:
    source = _replace_once(
        _source(),
        "                  if seen >= expected_files:\n",
        "                  if body:\n",
    )
    assert "prove completeness or fail closed" in _messages(source)


def test_rejects_fail_open_workflow_file_pagination_limit() -> None:
    source = _source()
    prefix, suffix = source.split("          def live_validation", 1)
    assert prefix.rstrip().endswith("return None")
    prefix = prefix.rstrip()[: -len("return None")] + "return False\n\n"
    source = prefix + "          def live_validation" + suffix
    assert "scan limit is exhausted" in _messages(source)


def test_rejects_loss_of_changed_file_count_contract() -> None:
    source = _replace_once(
        _source(),
        "              workflow_change = touches_workflows(number, pr.get('changed_files'))\n",
        "              workflow_change = touches_workflows(number, 1)\n",
    )
    assert "initial workflow-file exclusion must use the PR changed-file count" in _messages(source)


def test_rejects_loss_of_workflow_filter_recheck() -> None:
    source = _replace_once(
        _source(),
        "              if touches_workflows(number, fresh.get('changed_files')) is not False:\n",
        "              if False:\n",
    )
    assert "revalidated immediately before mutation" in _messages(source)


def test_rejects_missing_active_ci_state() -> None:
    source = _replace_once(_source(), "'waiting', ", "")
    assert "active CI detection missing status: waiting" in _messages(source)


def test_rejects_action_checkout() -> None:
    source = _replace_once(
        _source(),
        "    steps:\n      - name: Gate branch refresh on Actions pressure\n",
        "    steps:\n      - uses: actions/checkout@0000000000000000000000000000000000000000\n      - name: Gate branch refresh on Actions pressure\n",
    )
    assert "must remain checkout/action-free" in _messages(source)


def test_rejects_loss_of_mutation_cap() -> None:
    source = _replace_once(_source(), "          max_updates = 4", "          max_updates = 100")
    assert "bounded per-pass mutation cap" in _messages(source)


def test_rejects_loss_of_queue_pressure_guard() -> None:
    source = _replace_once(
        _source(),
        "      MAX_QUEUED_ACTIONS_RUNS: '40'\n",
        "",
    )
    assert "queue-pressure contract missing" in _messages(source)


def test_branch_control_plane_uses_general_runner_capacity() -> None:
    for workflow_name in (
        "branch-flow.yml",
        "branch-clean.yml",
        "branch-archive.yml",
        "branch-repair-100.yml",
    ):
        source = (
            REPO_ROOT / ".github" / "workflows" / workflow_name
        ).read_text(encoding="utf-8")
        assert "runs-on: ubuntu-latest" in source
        assert "runs-on: ubuntu-24.04-arm" not in source
