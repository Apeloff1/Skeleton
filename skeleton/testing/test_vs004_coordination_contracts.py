from __future__ import annotations
import hashlib,pytest
from skeleton.ai.agents.multi_agent_engineering import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
def task():return MultiAgentTask("TASK.100","parallel bounded build",("AUTH.READ","AUTH.WRITE"),("a","b"),2)
def assignment(i="ASSIGN.1",agent="AGENT.1",auth=("AUTH.READ",),paths=("a",)):return AgentAssignment(i,task().digest,agent,auth,paths,"LEASE.1")
def handoff():return HandoffPacket("HANDOFF.1","ASSIGN.1","AGENT.1",S("artifact"),S("state"),S("tests"),"rollback:1")
def test_subset_assignment_is_accepted():
 c=Coordinator(task());c.assign(assignment());assert "ASSIGN.1" in c.assignments
def test_authority_amplification_rejected():
 with pytest.raises(CoordinationError,match="authority exceeds"):Coordinator(task()).assign(assignment(auth=("AUTH.ROOT",)))
def test_scope_amplification_rejected():
 with pytest.raises(CoordinationError,match="scope exceeds"):Coordinator(task()).assign(assignment(paths=("outside",)))
def test_overlapping_mutation_domains_rejected():
 c=Coordinator(task());c.assign(assignment())
 with pytest.raises(CoordinationError,match="overlaps"):c.assign(assignment("ASSIGN.2","AGENT.2",paths=("a",)))
def test_handoff_must_come_from_assigned_agent():
 c=Coordinator(task());c.assign(assignment());bad=HandoffPacket("HANDOFF.1","ASSIGN.1","AGENT.2",S("a"),S("s"),S("t"),"rollback")
 with pytest.raises(CoordinationError,match="producer mismatch"):c.accept_handoff(bad)
def test_handoff_verifier_is_independent():
 h=handoff()
 with pytest.raises(CoordinationError,match="independent"):HandoffVerification(h.digest,"AGENT.1","AGENT.1",True)
def test_partial_failure_blocks_commit():
 c=Coordinator(task());c.assign(assignment());h=handoff();c.accept_handoff(h);v=HandoffVerification(h.digest,"AGENT.VERIFY","AGENT.1",True);c.fail("ASSIGN.1");assert not c.can_commit((v,))

def test_commit_requires_exact_accepted_handoff_verification():
 c=Coordinator(task());c.assign(assignment());h=handoff()
 unrelated=HandoffVerification(S("other"),"AGENT.VERIFY","AGENT.1",True)
 assert not c.can_commit((unrelated,))
 c.accept_handoff(h);assert not c.can_commit((unrelated,))
 good=HandoffVerification(h.digest,"AGENT.VERIFY","AGENT.1",True);assert c.can_commit((good,))
def test_duplicate_or_failed_verification_cannot_satisfy_commit():
 c=Coordinator(task());c.assign(assignment());h=handoff();c.accept_handoff(h)
 good=HandoffVerification(h.digest,"AGENT.VERIFY","AGENT.1",True)
 failed=HandoffVerification(h.digest,"AGENT.VERIFY2","AGENT.1",False)
 assert not c.can_commit((good,good));assert not c.can_commit((failed,))
def test_handoff_is_immutable_per_assignment():
 c=Coordinator(task());c.assign(assignment());c.accept_handoff(handoff())
 changed=HandoffPacket("HANDOFF.2","ASSIGN.1","AGENT.1",S("different"),S("state"),S("tests"),"rollback:1")
 with pytest.raises(CoordinationError,match="immutable"):c.accept_handoff(changed)
def test_failed_assignment_can_recover_only_with_new_agent_lease_same_domain():
 c=Coordinator(task());a=assignment();c.assign(a);c.fail(a.assignment_id)
 same=AgentAssignment(a.assignment_id,a.task_digest,"AGENT.2",a.authority_ids,a.scope_paths,a.lease_id)
 with pytest.raises(CoordinationError,match="new agent and lease"):c.recover(a.assignment_id,same)
 changed=AgentAssignment(a.assignment_id,a.task_digest,"AGENT.2",a.authority_ids,("b",),"LEASE.2")
 with pytest.raises(CoordinationError,match="cannot amplify or alter"):c.recover(a.assignment_id,changed)
 replacement=AgentAssignment(a.assignment_id,a.task_digest,"AGENT.2",a.authority_ids,a.scope_paths,"LEASE.2")
 c.recover(a.assignment_id,replacement);assert a.assignment_id not in c.failed
def test_verification_passed_must_be_strict_boolean():
 h=handoff()
 with pytest.raises(CoordinationError,match="passed must be bool"):HandoffVerification(h.digest,"AGENT.VERIFY","AGENT.1",1)
