import pytest
from skeleton.automation.ci_evidence import Gate,CIEvidence
def test_green_exact_head():
 e=CIEvidence("a"*40,(Gate("CI/CD","completed","success",1),),("CI/CD",));assert e.green() and len(e.digest())==64
def test_pending_not_green():
 assert not CIEvidence("a"*40,(Gate("CI/CD","pending",None,1),),("CI/CD",)).green()
def test_missing_required_fails():
 with pytest.raises(ValueError):CIEvidence("a"*40,(),("CI/CD",)).green()
