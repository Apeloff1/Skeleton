from pathlib import Path


WORKFLOW = Path(".github/workflows/ci.yml")


def test_java_accelerator_bridge_installs_skeleton_config_runtime() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    java_job = workflow.split("  java-accelerators:\n", 1)[1].split(
        "\n  school-jeeves-test:", 1
    )[0]
    bridge = java_job.split("- name: Python bridge and fallback tests", 1)[1]

    assert '"pytest>=8,<9"' in bridge
    assert '"pydantic>=2.5,<3"' in bridge
    assert '"pydantic-settings>=2.1,<3"' in bridge
    assert "skeleton/testing/test_jvm_observability_accelerator.py" in bridge
    assert "skeleton/testing/test_jvm_accelerator_runtime_status.py" in bridge


def test_java_accelerator_dependencies_are_installed_before_collection() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    java_job = workflow.split("  java-accelerators:\n", 1)[1].split(
        "\n  school-jeeves-test:", 1
    )[0]

    install = java_job.index("python -m pip install")
    pytest = java_job.index("python -m pytest -q")
    assert install < pytest
