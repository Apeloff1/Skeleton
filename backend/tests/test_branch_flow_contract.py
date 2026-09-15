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
    source = _replace_once(_source(), "  push:\n    branches: [main]\n", "  push:\n    branches: [main]\n  pull_request:\n    types: [synchronize]\n")
    assert "must never run on pull-request events" in _messages(source)


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
    source = _replace_once(_source(), "          def touches_workflows(number):", "          def touches_other_files(number):")
    assert "inspect changed files for workflow control-plane changes" in _messages(source)


def test_rejects_loss_of_workflow_filter_recheck() -> None:
    source = _replace_once(
        _source(),
        "              if touches_workflows(number) is not False:\n",
        "              if False:\n",
    )
    assert "revalidated immediately before mutation" in _messages(source)


def test_rejects_fail_open_workflow_file_pagination_limit() -> None:
    source = _replace_once(
        _source(),
        "              return None\n\n          def live_validation",
        "              return False\n\n          def live_validation",
    )
    assert "scan limit is exhausted" in _messages(source)


def test_rejects_missing_active_ci_state() -> None:
    source = _replace_once(_source(), "'waiting', ", "")
    assert "active CI detection missing status: waiting" in _messages(source)


def test_rejects_action_checkout() -> None:
    source = _replace_once(
        _source(),
        "    steps:\n      - name: Advance only stable same-repository PR branches\n",
        "    steps:\n      - uses: actions/checkout@0000000000000000000000000000000000000000\n      - name: Advance only stable same-repository PR branches\n",
    )
    assert "must remain checkout/action-free" in _messages(source)


def test_rejects_loss_of_mutation_cap() -> None:
    source = _replace_once(_source(), "          max_updates = 4", "          max_updates = 100")
    assert "bounded per-pass mutation cap" in _messages(source)
