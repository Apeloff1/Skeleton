"""Regression for immutable main-SHA CI evidence in the core workflows."""
from __future__ import annotations

from scripts.check_ci_concurrency_custody import WORKFLOWS, validate, validate_text

GROUP = "$" + "{{ github.event.pull_request.number || github.sha }}"
CANCEL = "$" + "{{ github.event_name == 'pull_request' }}"


def template(name: str) -> str:
    prefix = WORKFLOWS[name]
    return (
        "name: Test\n"
        "on: push\n"
        "concurrency:\n"
        f"  group: {prefix}-{GROUP}\n"
        f"  cancel-in-progress: {CANCEL}\n"
        "jobs:\n  audit:\n    runs-on: ubuntu-latest\n"
    )


def test_live_core_workflow_concurrency_contract() -> None:
    assert validate() == []


def test_good_contract_for_each_required_workflow() -> None:
    for name in WORKFLOWS:
        assert validate_text(name, template(name)) == []


def test_main_ref_based_cancellation_fails_closed() -> None:
    for name in WORKFLOWS:
        broken = template(name).replace("github.sha", "github.ref")
        assert any("grouping drifted" in issue for issue in validate_text(name, broken))


def test_permanent_cancel_in_progress_true_fails_closed() -> None:
    for name in WORKFLOWS:
        broken = template(name).replace(CANCEL, "true")
        assert any("must not be cancelled" in issue for issue in validate_text(name, broken))


def test_missing_and_duplicate_concurrency_rejected() -> None:
    for name in WORKFLOWS:
        assert validate_text(name, "name: Test\non: push\n")
        broken = template(name).replace("  cancel-in-progress:", "  group: duplicate\n  cancel-in-progress:")
        assert any("duplicated group" in issue for issue in validate_text(name, broken))


def test_unreviewed_workflow_refused() -> None:
    assert validate_text("unknown.yml", "concurrency:\n") == ["unknown.yml: unreviewed workflow"]
