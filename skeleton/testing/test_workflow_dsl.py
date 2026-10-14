from skeleton.ai.workflow_dsl import *
def test_valid_source_parses_only_declared_privilege():
 s=WorkflowSource(DSLVersion.V1,"step a capability=repo.read authority=worker.bounded")
 steps,d=parse_workflow(s,{"repo.read"},{"worker.bounded"});assert len(steps)==1 and not d
def test_undeclared_capability_or_authority_fails_closed():
 for text in ("step a capability=repo.write authority=worker.bounded","step a capability=repo.read authority=admin"):
  steps,d=parse_workflow(WorkflowSource(DSLVersion.V1,text),{"repo.read"},{"worker.bounded"})
  assert not steps and d
def test_injection_and_ambiguous_syntax_rejected():
 steps,d=parse_workflow(WorkflowSource(DSLVersion.V1,"step a capability=repo.read authority=worker.bounded; rm"),{"repo.read"},{"worker.bounded"})
 assert not steps and d[0].code=="syntax"
def test_duplicate_steps_fail_closed():
 s=WorkflowSource(DSLVersion.V1,"step a capability=x authority=y\nstep a capability=x authority=y")
 steps,d=parse_workflow(s,{"x"},{"y"});assert not steps and d[0].code=="duplicate-step"
