"""Regression contract for pytest package import precedence in Full Regression."""

from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/full-regression-gate.yml"


def test_backend_pytest_uses_backend_first_pythonpath():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert 'if [[ "${suite}" == "backend/tests" ]]; then' in workflow
    assert 'suite_pythonpath="${GITHUB_WORKSPACE}/backend:${GITHUB_WORKSPACE}"' in workflow
    assert 'PYTHONPATH="${suite_pythonpath}" pytest' in workflow


def test_root_pytest_keeps_root_first_imports():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert 'suite_pythonpath="${GITHUB_WORKSPACE}:${GITHUB_WORKSPACE}/backend"' in workflow
    assert "for suite in tests skeleton/testing backend/tests; do" in workflow
    assert '"${suite}"' in workflow


def test_pytest_entrypoint_preserves_pythonpath_precedence():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert 'PYTHONPATH="${suite_pythonpath}" pytest -q' in workflow
    assert 'PYTHONPATH="${suite_pythonpath}" python -m pytest' not in workflow


def test_backend_pytest_preserves_configured_marker_registry():
    """A CLI markers override hides backend's unit/integration markers in strict mode."""
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert 'marker_args=(-o "markers=live_service:' in workflow
    assert 'if [[ "${suite}" == "backend/tests" ]]; then' in workflow
    assert 'marker_args=()' in workflow
    assert '"${marker_args[@]}"' in workflow
    assert '-o "markers=live_service: requires a separately running or remote backend service" \\' not in workflow


def test_backend_pytest_config_registers_required_markers():
    config = (WORKFLOW.parents[2] / "backend/pyproject.toml").read_text(encoding="utf-8")
    for marker in ("unit:", "integration:", "live_service:", "timeout(seconds):"):
        assert marker in config


def test_isolated_suites_can_import_sibling_fixture_modules():
    """Root and skeleton suites use top-level sibling fixture imports."""
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert 'if [[ "${suite}" == "tests" ]]; then' in workflow
    assert 'suite_pythonpath="${GITHUB_WORKSPACE}/tests:${suite_pythonpath}"' in workflow
    assert 'elif [[ "${suite}" == "skeleton/testing" ]]; then' in workflow
    assert 'suite_pythonpath="${GITHUB_WORKSPACE}/skeleton/testing:${suite_pythonpath}"' in workflow
    assert 'suite_pythonpath="${GITHUB_WORKSPACE}/backend:${GITHUB_WORKSPACE}"' in workflow
