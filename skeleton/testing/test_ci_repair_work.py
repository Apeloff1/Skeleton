from skeleton.automation.ci_repair_work import derive
def test_repair_identity_is_exact_head_bound():
 a=derive("Backend Quality",7,"a"*40);b=derive("Backend Quality",7,"b"*40);assert a.id!=b.id
def test_objective_forbids_gate_weakening():assert "without weakening" in derive("CI/CD",1,"a"*40).objective
