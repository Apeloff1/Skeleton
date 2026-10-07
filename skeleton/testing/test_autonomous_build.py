import pytest
from skeleton.automation.autonomous_build import BuildState,advance,should_continue
def sup(q=2,terminal=False,fp="a"*64):
 return {"team":"night","issue_number":1,"generation_id":"g","progress":{"fingerprint_sha256":fp,"terminal":terminal,"counts":{"queued":q,"blocked":0}}}
def test_continues_validated_work():
 s=advance(BuildState(),supervisor=sup(),validated=True,outcome_sha="b"*64); assert should_continue(s) and s.accepted==1
def test_completes_when_queue_drained():
 s=advance(BuildState(),supervisor=sup(0,True),validated=True); assert s.status=="complete"
def test_stagnation_quarantines():
 s=BuildState()
 for _ in range(6): s=advance(s,supervisor=sup(),validated=True,max_stagnant=5)
 assert s.status=="quarantined"
def test_failure_budget_quarantines():
 s=BuildState()
 for i in range(2): s=advance(s,supervisor=sup(fp=(str(i)*64)[:64]),validated=False,max_failures=2)
 assert s.status=="quarantined"
