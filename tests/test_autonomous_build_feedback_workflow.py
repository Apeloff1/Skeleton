from pathlib import Path

WORKFLOW = Path(".github/workflows/autonomous-build-feedback.yml")
GOOD_PIN = "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1"
BAD_PIN = "actions/upload-artifact@ea165f8d65b6e75b5404495eeb8b5cf9c8f1f1a2"


def test_autonomous_build_feedback_uses_resolvable_node24_upload_artifact_pin() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert GOOD_PIN in text
    assert BAD_PIN not in text


def test_autonomous_build_feedback_installs_pytest_before_validation() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    install = text.index("Install feedback control plane test dependencies")
    validate = text.index("Validate feedback control plane\n")
    assert install < validate
    install_block = text[install:validate]
    for requirement in ('"pytest>=8,<9"', '"pydantic>=2.5,<3"', '"pydantic-settings>=2.1,<3"'):
        assert requirement in install_block
