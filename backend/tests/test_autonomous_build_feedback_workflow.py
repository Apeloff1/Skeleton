from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "autonomous-build-feedback.yml"


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_feedback_workflow_bootstraps_pytest_before_validation() -> None:
    text = _workflow_text()

    install = "python -m pip install --disable-pip-version-check 'pytest>=7.0.0'"
    validate = "python -m pytest -q"

    assert install in text
    assert validate in text
    assert text.index(install) < text.index(validate)


def test_feedback_workflow_keeps_exact_head_and_credential_boundaries() -> None:
    text = _workflow_text()

    assert "persist-credentials: false" in text
    assert 'test "$(git rev-parse HEAD)" = "$HEAD_SHA"' in text
    assert "GH_TOKEN: ''" in text
    assert "GITHUB_TOKEN: ''" in text


def test_feedback_workflow_keeps_artifact_pin_and_fail_closed_publish() -> None:
    text = _workflow_text()

    assert (
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
        in text
    )
    assert "if-no-files-found: error" in text
