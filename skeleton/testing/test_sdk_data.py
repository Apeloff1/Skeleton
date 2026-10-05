from skeleton.ai.runtime.deferred.sdk_data import *
def test_internal_sdk_hides_deprecated_boundary():
 s=InternalSDK("1",(SDKExport("public","v1"),SDKExport("_old","v0",True)))
 assert supported_export(s,"public") and supported_export(s,"_old") is None
def test_provider_native_objects_must_terminate_at_adapter():
 assert provider_conformant(ProviderConformance(True,True,False))
 assert not provider_conformant(ProviderConformance(True,True,True))
def test_storage_selection_uses_declared_state_and_consistency():
 a=StoreHandle("db",StateClass.DURABLE,Consistency.STRONG,True,True,True)
 assert select_store(StorageSDK((a,)),StateClass.DURABLE,Consistency.STRONG)==a
 try:select_store(StorageSDK((a,)),StateClass.BLOB,Consistency.STRONG);assert False
 except ValueError:pass
def test_event_consumers_require_version_match_and_idempotency():
 p=EventPublisher("p","v1")
 assert event_compatible(p,EventConsumer("c","v1",True,True))
 assert not event_compatible(p,EventConsumer("c","v1",True,False))
 assert not event_compatible(p,EventConsumer("c","v2",True,True))
def test_evaluation_result_captures_environment_model_config_identity():
 sdk=EvaluationSDK("env","model",{"temp":0});s=Scorer("acc","1",("x",),("score",),("numpy",))
 r=record_evaluation(sdk,s,.9);assert (r.environment_id,r.model_id,r.scorer_version)==("env","model","1") and r.config_digest
def test_benchmark_cannot_bypass_dataset_security_or_resources():
 p=BenchmarkPlugin("b",BenchmarkManifest("1","d","7",("gpu",)))
 assert not admit_benchmark(p,dataset_rights=False,security_allowed=True,resources_allowed=True).admitted
 assert not admit_benchmark(p,dataset_rights=True,security_allowed=False,resources_allowed=True).admitted
 assert admit_benchmark(p,dataset_rights=True,security_allowed=True,resources_allowed=True).dataset_version=="7"
def test_breaking_data_change_requires_migration():
 f=DataField("x","count",False,"items","1h","internal");old=DataContract("d","1",(f,),(DataConsumer("c","1"),))
 new=DataContract("d","2",(),(DataConsumer("c","1"),))
 assert breaking_change(old,new,migration_declared=False)
 assert not breaking_change(old,new,migration_declared=True)
