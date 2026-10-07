from skeleton.automation.repair_authority import authorize
from skeleton.automation.ci_repair_queue import CIRepairTask
def t(head="a"*40):return CIRepairTask("x","CI/CD","code_quality",head,1,2,"b"*64,"repair")
def test_stale_head_rejected():assert not authorize(t("b"*40),current_head="a"*40,allowed_categories={"code_quality"}).authorized
def test_allowed_exact_head():assert authorize(t(),current_head="a"*40,allowed_categories={"code_quality"}).authorized
