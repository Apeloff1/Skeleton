import pytest
from skeleton.automation.build_certifier import CertificationInput,certify
from skeleton.automation.ci_evidence import CIEvidence,Gate
def inp():return CertificationInput("id","a"*40,"b"*40,2,1,("c"*64,),True,True,True,True)
def test_certifies_only_green_exact_head():
 c=certify(inp(),CIEvidence("b"*40,(Gate("CI/CD","completed","success",1),),("CI/CD",)));assert c.status=="complete"
def test_wrong_head_rejected():
 with pytest.raises(ValueError):certify(inp(),CIEvidence("d"*40,(Gate("CI/CD","completed","success",1),),("CI/CD",)))
