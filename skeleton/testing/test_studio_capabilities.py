import pytest
from skeleton.automation.studio_capabilities import capability_for, validate_capabilities

def test_python_creation_and_test_creation_are_distinct():
    assert capability_for("skeleton/new.py",creating=True)=="python.create"
    assert capability_for("skeleton/testing/test_new.py",creating=True)=="tests.create"

def test_unknown_extension_fails_closed():
    with pytest.raises(ValueError): capability_for("skeleton/tool.sh",creating=True)

def test_validate_capabilities_preserves_path_order():
    assert validate_capabilities(["docs/a.md","skeleton/a.py"],new_paths=["skeleton/a.py"])==("docs.modify","python.create")
