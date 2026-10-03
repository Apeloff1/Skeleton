from skeleton.automation.repair_admission import admit
from skeleton.automation.ci_repair_queue import CIRepairTask
def t():return CIRepairTask("r","CI/CD","code_quality","a"*40,1,2,"b"*64,"repair")
def test_requires_canonical_identity():assert not admit(t(),head_sha="a"*40,supervisor_generation="g",authorized_gates={"CI/CD"}).accepted
def test_authorized_admission():assert admit(t(),head_sha="a"*40,supervisor_generation="g",authorized_gates={"CI/CD"},canonical_task_id="task-1").accepted
