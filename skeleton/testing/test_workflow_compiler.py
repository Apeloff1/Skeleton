from skeleton.ai.workflow_compiler import *
def test_compilation_is_deterministic():
 a=compile_workflow("w",["b","a"],[WorkflowLink("a","b")],["read"],{"read"},{})
 b=compile_workflow("w",["a","b"],[WorkflowLink("a","b")],["read"],{"read"},{})
 assert a.ok and a.workflow.digest==b.workflow.digest
def test_missing_capability_rejected_before_runtime():
 r=compile_workflow("w",["a"],[],["write"],{"read"},{})
 assert not r.ok and "missing-capability:write" in r.diagnostics
def test_cycle_rejected():
 r=compile_workflow("w",["a","b"],[WorkflowLink("a","b"),WorkflowLink("b","a")],[],set(),{})
 assert not r.ok and "cycle" in r.diagnostics
def test_invalid_compensation_rejected():
 r=compile_workflow("w",["a"],[],[],set(),{"a":"missing"})
 assert not r.ok and "invalid-compensation:a" in r.diagnostics

def test_generator_nodes_are_not_consumed_twice():
 r=compile_workflow("w",(x for x in ("a","b")),(),(),(),{})
 assert r.ok and r.workflow.nodes==("a","b")
def test_missing_workflow_identity_fails_closed():assert not compile_workflow("",("a",),(),(),(),{}).ok
