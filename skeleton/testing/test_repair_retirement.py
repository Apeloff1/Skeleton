from skeleton.automation.repair_retirement import evaluate
def test_requires_new_head_and_green_gate():assert evaluate(repair_id="r",original_gate="CI/CD",original_head="a",current_head="b",current_gate_green=True,receipt_verified=True).retired
def test_same_head_not_retired():assert not evaluate(repair_id="r",original_gate="CI/CD",original_head="a",current_head="a",current_gate_green=True,receipt_verified=True).retired
