"""Regression contract for pytest package import precedence in Full Regression."""

from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/full-regression-gate.yml"


def test_backend_pytest_uses_backend_first_pythonpath():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert 'if [[ "${suite}" == "backend/tests" ]]; then' in workflow
    assert 'suite_pythonpath="${GITHUB_WORKSPACE}/backend:${GITHUB_WORKSPACE}"' in workflow
    assert 'PYTHONPATH="${suite_pythonpath}" python -m pytest' in workflow


def test_root_pytest_keeps_root_first_imports():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert 'suite_pythonpath="${GITHUB_WORKSPACE}:${GITHUB_WORKSPACE}/backend"' in workflow
    assert "for suite in tests skeleton/testing backend/tests; do" in workflow
    assert '"\${suite}"' not in workflow  # pytest receives the expanded suite path
    assert '"${suite}"' in workflow
