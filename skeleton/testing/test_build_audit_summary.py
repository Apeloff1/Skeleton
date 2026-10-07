import json
from skeleton.automation.build_audit_summary import AuditSummary,render
def test_summary():assert json.loads(render(AuditSummary("a"*40,"complete",2,1,0,0)))["status"]=="complete"
