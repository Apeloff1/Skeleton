from skeleton.security.tool_result_trust import *
def test_tool_output_never_becomes_instruction():assert not validate_result(ToolResultTrust("x",(),True)).valid
def test_high_impact_requires_independent_evidence():assert not validate_result(ToolResultTrust("x",(ToolEvidence("tool",1,False),)),True).valid
