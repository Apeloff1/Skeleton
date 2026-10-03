from skeleton.automation.ci_feedback import build_feedback
def run(id,name,status="completed",conclusion="failure"):return {"id":id,"name":name,"status":status,"conclusion":conclusion}
def test_failure_with_log_creates_repair():
 f=build_feedback(head_sha="a"*40,runs=(run(1,"Backend Quality"),),required=("Backend Quality",),job_logs={1:(7,"ERROR broken")})
 assert len(f.repairs)==1 and not f.quarantined
def test_security_failure_quarantines():
 f=build_feedback(head_sha="a"*40,runs=(run(1,"Workflow Input Security"),),required=("Workflow Input Security",),job_logs={1:(7,"ERROR unsafe")})
 assert f.quarantined==("Workflow Input Security",) and not f.repairs
def test_missing_failed_log_fails_closed():
 f=build_feedback(head_sha="a"*40,runs=(run(1,"Backend Quality"),),required=("Backend Quality",),job_logs={})
 assert f.quarantined==("Backend Quality",)
def test_pending_is_not_repair():
 f=build_feedback(head_sha="a"*40,runs=(run(1,"CI/CD","queued",None),),required=("CI/CD",),job_logs={})
 assert f.pending==("CI/CD",) and not f.repairs
