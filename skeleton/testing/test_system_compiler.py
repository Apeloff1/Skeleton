from skeleton.ai.system_compiler import *
def test_generation_is_deterministic_and_traceable():
 s=SystemSource("c","v1",{"b":2,"a":1});a=compile_system(s,SystemCompilePlan(("z","a")));b=compile_system(s,SystemCompilePlan(("a","z")))
 assert a==b and all(x.source_digest==a[0].source_digest for x in a)
def test_generated_artifact_never_grants_authority():
 assert all(x.derived and not x.grants_authority for x in compile_system(SystemSource("c","v1",{}),SystemCompilePlan(("x",))))
