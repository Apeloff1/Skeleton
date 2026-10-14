import pytest
from skeleton.ai.runtime.deferred.lifecycle_safety import *
D="a"*64
def step(i,key="k"): return MigrationStep(i,D,key,D)
def test_idempotent_migration_requires_keys():
 with pytest.raises(ValueError): MigrationPlan("m","1","2",MigrationMode.IDEMPOTENT,False,(step("s",None),))
def test_resume_rejects_other_plan():
 p=MigrationPlan("m","1","2",MigrationMode.IDEMPOTENT,False,(step("s"),)); e=MigrationEngine(p); r=e.apply_next()
 other=MigrationEngine(MigrationPlan("m","1","3",MigrationMode.IDEMPOTENT,False,(step("s"),)))
 with pytest.raises(ValueError): other.resume(r)
def test_checkpoint_must_be_prefix():
 p=MigrationPlan("m","1","2",MigrationMode.IDEMPOTENT,True,(step("a","a"),step("b","b"))); e=MigrationEngine(p)
 with pytest.raises(ValueError): e.resume(MigrationReceipt("m",e.identity,MigrationState.RUNNING,("b",),1))
def test_resume_completes_deterministically():
 p=MigrationPlan("m","1","2",MigrationMode.IDEMPOTENT,True,(step("a","a"),step("b","b"))); e=MigrationEngine(p)
 r=e.apply_next(); x=MigrationEngine(p); x.resume(r); assert x.apply_next().state is MigrationState.COMPLETE
def test_adapter_cannot_mint_authority():
 with pytest.raises(ValueError): CompatibilityAdapter("a","canonical",("admin",))
def test_removal_needs_parity_and_no_supported_consumer():
 a=CompatibilityAdapter("a","canonical"); p=ParityEvidence("a",D,D,D)
 assert not can_remove_adapter(a,(LegacyConsumer("c","a","r"),),p)
 assert can_remove_adapter(a,(LegacyConsumer("c","a","r",False),),p)
 assert not can_remove_adapter(a,(),ParityEvidence("a",D,"b"*64,D))
def test_retirement_blocks_supported_consumers():
 d=Deprecation("f",DeprecationState.DEPRECATED,DeprecationWindow("r1","r3"),"p")
 r=decide_retirement(d,(LegacyConsumer("c","a","r2"),)); assert not r.allowed and r.consumer_ids==("c",)
def test_policy_break_is_explicit():
 d=Deprecation("f",DeprecationState.DEPRECATED,DeprecationWindow("r1","r3"),"p")
 assert decide_retirement(d,(LegacyConsumer("c","a","r2"),),policy_break=True).allowed
def test_active_feature_cannot_retire():
 d=Deprecation("f",DeprecationState.ACTIVE,DeprecationWindow("r1","r3"),"p")
 assert not decide_retirement(d,()).allowed
