from skeleton.automation.studio_validation import plan_validation

def test_direct_test_is_preferred():
    p=plan_validation(["skeleton/testing/test_a.py"],["skeleton/testing/test_b.py"])
    assert "test_a.py" in p.commands[0][-1]

def test_related_test_used_for_source():
    p=plan_validation(["skeleton/a.py"],["skeleton/testing/test_a.py"])
    assert p.commands[0][-1]=="skeleton/testing/test_a.py"
    assert p.commands[1][:3]==("python","-m","compileall")

def test_non_python_has_no_python_validation():
    assert plan_validation(["docs/a.md"]).commands==()
