from skeleton.automation.ci_log_evidence import extract
from skeleton.automation.ci_repair_queue import task_from,dedupe
def test_retryable_failure_becomes_head_bound_task():
 e=extract(run_id=1,job_id=2,gate="Backend Quality",head_sha="a"*40,log="ERROR x")
 t=task_from(e);assert t and t.head_sha=="a"*40 and "preserve" in t.objective
def test_security_failure_not_auto_repaired():
 e=extract(run_id=1,job_id=2,gate="Workflow Input Security",head_sha="a"*40,log="ERROR x")
 assert task_from(e) is None
def test_dedupe():
 e=extract(run_id=1,job_id=2,gate="CI/CD",head_sha="a"*40,log="ERROR x");t=task_from(e)
 assert len(dedupe((t,t)))==1
