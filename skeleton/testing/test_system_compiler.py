from skeleton.ai.system_compiler import *
def test_generation_is_deterministic_and_traceable():
 s=SystemSource("c","v1",{"b":2,"a":1});a=compile_system(s,SystemCompilePlan(("z","a")));b=compile_system(s,SystemCompilePlan(("a","z")))
 assert a==b and all(x.source_digest==a[0].source_digest for x in a)
def test_generated_artifact_never_grants_authority():
 assert all(x.derived and not x.grants_authority for x in compile_system(SystemSource("c","v1",{}),SystemCompilePlan(("x",))))

def test_nonfinite_source_rejected():
 import pytest,math
 with pytest.raises(ValueError):compile_system(SystemSource("c","v",{"x":math.nan}),SystemCompilePlan(("py",)))
def test_artifact_cannot_be_constructed_authoritative():
 import pytest
 with pytest.raises(ValueError):SystemArtifact("x",b"x","d",True,True)

def test_empty_target_identity_rejected():
 import pytest
 with pytest.raises(ValueError):compile_system(SystemSource("c","v",{}),SystemCompilePlan(("",)))
