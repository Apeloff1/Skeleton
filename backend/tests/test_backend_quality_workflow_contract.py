from __future__ import annotations

from pathlib import Path


def _workflow_text() -> str:
    root = Path(__file__).resolve().parents[2]
    return (root / ".github/workflows/backend-quality.yml").read_text(encoding="utf-8")


def test_repository_wide_adversarial_regressions_run_from_workspace_root() -> None:
    workflow = _workflow_text()

    step = workflow[
        workflow.index(
            "- name: Security, provider-chaos, and developer-tooling adversarial regression tests"
        ):
    ]
    step_header = step.split("      - name:", 1)[0]
    assert "working-directory: ${{ github.workspace }}" in step_header
    assert "working-directory: ." not in step_header
    assert "working-directory: .." not in step_header
    assert "PYTHONPATH=.:backend python -m pytest" in step
    assert "--rootdir=." in step
    assert "--import-mode=importlib" in step
    assert "tests/test_architecture_boundaries.py" in step
