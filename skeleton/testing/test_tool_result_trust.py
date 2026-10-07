from skeleton.security.tool_result_trust import *
def test_tool_output_never_becomes_instruction():assert not validate_result(ToolResultTrust("x",(),True)).valid
def test_high_impact_requires_independent_evidence():assert not validate_result(ToolResultTrust("x",(ToolEvidence("tool",1,False),)),True).valid

def test_verified_level_requires_independent_provenance():assert not validate_result(ToolResultTrust("verified",(ToolEvidence("s",1,False),))).valid
def test_future_provenance_rejected():assert not validate_result(ToolResultTrust("context",(ToolEvidence("s",11,True),)),now=10,max_age=5).valid
