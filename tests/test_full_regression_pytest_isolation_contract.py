"""Guard against reintroducing cross-package pytest collection collisions."""

from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/full-regression-gate.yml"


def test_full_regression_collects_each_tree_in_a_fresh_pytest_process():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "for suite in tests skeleton/testing backend/tests; do" in workflow
    assert 'python -m pytest -q --tb=short \\' in workflow
    assert '"${suite}"' in workflow
    assert "set -euo pipefail" in workflow
    assert '-m "not live_service"' in workflow


def test_full_regression_keeps_per_tree_junit_evidence():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert '--junitxml="artifacts/python-regression-${report}.junit.xml"' in workflow
    assert "path: artifacts/python-regression-*.junit.xml" in workflow
    assert "if-no-files-found: error" in workflow
