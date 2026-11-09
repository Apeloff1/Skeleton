import hashlib,pytest
from skeleton.ai.tool_discovery import ToolCapability,ManifestAttestation,ToolManifest,validate_manifest
from skeleton.security.tool_result_trust import ToolEvidence,ToolResultTrust
from skeleton.ai.tool_trust_admission import admit_tool_result
D=hashlib.sha256(b"x").hexdigest()
def discovery(): return validate_manifest(ToolManifest("tool",(ToolCapability("read","v1"),),True,ManifestAttestation("root",D,True)),{"read"})
def test_verified_result_admitted_without_instruction_authority():
 a=admit_tool_result(discovery(),"read",ToolResultTrust("verified",(ToolEvidence("eval",10,True),)),D,high_impact=True,now=11,max_age=5)
 assert a.tool_id=="tool" and len(a.admission_digest)==64
def test_tool_output_never_becomes_instruction_authority():
 with pytest.raises(PermissionError,match="instruction"): admit_tool_result(discovery(),"read",ToolResultTrust("verified",(ToolEvidence("eval",10,True),),True),D,high_impact=True,now=11,max_age=5)
def test_high_impact_requires_independent_evidence():
 with pytest.raises(PermissionError,match="independent"): admit_tool_result(discovery(),"read",ToolResultTrust("context",(ToolEvidence("tool",10,False),)),D,high_impact=True,now=11,max_age=5)
