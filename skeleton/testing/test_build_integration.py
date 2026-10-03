from skeleton.automation.build_integration import integration_commands
def test_automation_change_gets_aggregate_regression():
 c=integration_commands(["skeleton/automation/a.py"]); assert any("test_supervised_studio.py" in x for cmd in c for x in cmd)
def test_plan_deterministic():
 p=["skeleton/testing/test_b.py","skeleton/a.py"]; assert integration_commands(p)==integration_commands(reversed(p))
