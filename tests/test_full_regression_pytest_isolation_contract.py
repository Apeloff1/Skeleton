"""Guard against reintroducing cross-package pytest collection collisions."""

from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/full-regression-gate.yml"


def test_full_regression_collects_each_tree_in_a_fresh_pytest_process():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "for suite in tests skeleton/testing backend/tests; do" in workflow
    assert 'pytest -q --tb=short \\' in workflow
    assert '"${suite}"' in workflow
    assert "set -euo pipefail" in workflow
    assert '-m "not live_service"' in workflow


def test_full_regression_keeps_per_tree_junit_evidence():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert '--junitxml="artifacts/python-regression-${report}.junit.xml"' in workflow
    assert "path: artifacts/python-regression-*.junit.xml" in workflow
    assert "if-no-files-found: error" in workflow


def test_full_regression_reports_all_independent_suite_failures():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "suite_failures=0" in workflow
    assert 'if ! PYTHONPATH="${suite_pythonpath}" pytest' in workflow
    assert 'suite_failures=$((suite_failures + 1))' in workflow
    assert 'if (( suite_failures > 0 )); then' in workflow
    assert 'exit 1' in workflow
    assert '::error title=Python regression failed::' in workflow


def test_pytest_step_comments_are_separate_shell_lines():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "# root working directory to sys.path" in workflow
    assert "# PYTHONPATH when both root/tests" in workflow
    assert "# Keep collecting independent trees" in workflow
    # A literal backslash-n inside a YAML shell comment silently swallows
    # subsequent explanatory lines and can conceal malformed script edits.
    assert r"\n            #" not in workflow


def test_stacked_collection_repair_is_eligible_for_exact_head_pr_ci():
    """The gate must run on the integration branch targeted by this repair PR."""
    workflow = WORKFLOW.read_text(encoding="utf-8")
    trigger = workflow.split("\non:\n", 1)[1].split("\npermissions:\n", 1)[0]
    assert "branches: [main, laneA/main-green-integration]" in trigger
    assert "types: [opened, synchronize, reopened, ready_for_review]" in trigger
    assert "push:\n    branches: [main]" in trigger
    assert "workflow_dispatch:" in trigger
