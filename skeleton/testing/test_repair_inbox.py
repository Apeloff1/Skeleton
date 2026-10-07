from skeleton.automation.repair_inbox import RepairInbox
from skeleton.automation.ci_repair_queue import CIRepairTask
def task():return CIRepairTask("x","CI/CD","code_quality","a"*40,1,2,"b"*64,"repair")
def test_inbox_deduplicates(tmp_path):
 i=RepairInbox.empty("a"*40).add((task(),task()));assert len(i.tasks)==1;i.write(tmp_path/"i.json");assert len(i.sha256)==64
