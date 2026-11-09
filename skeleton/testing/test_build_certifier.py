import pytest
from skeleton.automation.build_certifier import CertificationInput,certify,certify_with_proof
from skeleton.automation.ci_evidence import CIEvidence,Gate
def inp():return CertificationInput("id","a"*40,"b"*40,2,1,("c"*64,),True,True,True,True)
def test_certifies_only_green_exact_head():
 c=certify(inp(),CIEvidence("b"*40,(Gate("CI/CD","completed","success",1),),("CI/CD",)));assert c.status=="complete"
def test_wrong_head_rejected():
 with pytest.raises(ValueError):certify(inp(),CIEvidence("d"*40,(Gate("CI/CD","completed","success",1),),("CI/CD",)))

def test_certificate_emits_composite_completion_proof():
 ci=CIEvidence("b"*40,(Gate("CI/CD","completed","success",1),),("CI/CD",))
 cert,proof=certify_with_proof(inp(),ci,canonical_fingerprint="d"*64,build_state_sha256="e"*64,receipt_sha256=("f"*64,))
 assert cert.status=="complete"
 assert proof.head_sha=="b"*40
 assert len(proof.digest())==64

def test_unresolved_repair_blocks_certificate():
 ci=CIEvidence("b"*40,(Gate("CI/CD","completed","success",1),),("CI/CD",))
 with pytest.raises(ValueError):
  certify_with_proof(inp(),ci,canonical_fingerprint="d"*64,build_state_sha256="e"*64,receipt_sha256=("f"*64,),repair_states={"repair-1":"validating"})
