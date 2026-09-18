import pytest

from skeleton.automation.specialist_bots import safe_path, validate_generated_files


def test_specialist_generated_python_validation_never_executes_source():
    validate_generated_files([
        {"path": "skeleton/good.py", "content": "x = 1\n"}
    ])
    with pytest.raises(RuntimeError, match="generated Python is invalid"):
        validate_generated_files([
            {"path": "skeleton/bad.py", "content": "def broken(:\n"}
        ])


def test_specialist_path_boundary_rejects_control_plane_and_traversal():
    assert safe_path("skeleton/module.py")
    assert not safe_path(".github/workflows/evil.yml")
    assert not safe_path("skeleton/../secrets.txt")
    assert not safe_path("/tmp/escape.py")
