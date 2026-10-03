import pytest
from skeleton.automation.build_repair import RepairEvidence
def test_repair_evidence(): RepairEvidence("t",1,("python","-m","pytest"),"failure","a"*64).validate()
def test_missing_command_rejected():
 with pytest.raises(ValueError): RepairEvidence("t",1,(),"","a"*64).validate()
