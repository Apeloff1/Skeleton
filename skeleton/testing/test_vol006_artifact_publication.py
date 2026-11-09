import pytest
from skeleton.modeling import *
from skeleton.modeling.publication import TrainingCompletion,complete_execution,ArtifactPublisher,PublicationError,CompletionMismatch

H="a"*64
def setup():
    reg=ModelDevelopmentRegistry()
    ds=DatasetManifest("ds",H,"owned",H,"none","b"*64,"c"*64,("src",))
    dd=reg.add_dataset(ds)
    run=TrainingRun("run",(dd,),H,"b"*64,"c"*64,7,status="completed")
    reg.add_run(run)
    ex=TrainingExecution(run.run_digest,TrainingBudget(2,10,10),7)
    ex.record_step(StepReceipt(run.run_digest,1,H,"d"*64,3,4,{"loss":1.0}))
    return reg,run,ex

def artifact(run,aid="model",content="e"*64):
    return ModelArtifact(aid,content,run.run_digest,"f"*64,"weights")

def test_completion_binds_execution_and_atomic_publication():
    reg,run,ex=setup(); c=complete_execution(ex); a=artifact(run); p=ArtifactPublisher(reg)
    d=p.publish(run,c,a)
    assert p.verify(c,d) and reg.verify(d,reg.lineage(d))
    assert p.publish(run,c,a)==d

def test_completion_is_deterministic():
    _,r,a=setup(); _,r2,b=setup()
    assert complete_execution(a)==complete_execution(b)

def test_cross_run_and_seed_forgery_denied_without_registry_mutation():
    reg,run,ex=setup(); c=complete_execution(ex); p=ArtifactPublisher(reg); before=reg.snapshot_digest()
    bad=TrainingRun("other",run.dataset_digests,H,"b"*64,"c"*64,7,status="completed")
    with pytest.raises(CompletionMismatch): p.publish(bad,c,artifact(bad))
    assert reg.snapshot_digest()==before
    forged=TrainingCompletion(c.run_digest,c.final_state_digest,c.receipt_digests,8,c.tokens,c.compute_units)
    with pytest.raises(CompletionMismatch): p.publish(run,forged,artifact(run))
    assert reg.snapshot_digest()==before

def test_one_completion_cannot_publish_two_artifacts():
    reg,run,ex=setup(); c=complete_execution(ex); p=ArtifactPublisher(reg)
    p.publish(run,c,artifact(run))
    with pytest.raises(CompletionMismatch): p.publish(run,c,artifact(run,"model2","1"*64))

def test_unknown_registry_run_fails_without_publisher_binding():
    reg,run,ex=setup(); c=complete_execution(ex)
    empty=ModelDevelopmentRegistry(); p=ArtifactPublisher(empty)
    with pytest.raises(LineageError): p.publish(run,c,artifact(run))
    assert not p.verify(c,artifact(run).artifact_digest)

def test_double_completion_and_authority_escalation_denied():
    _,_,ex=setup(); c=complete_execution(ex)
    with pytest.raises(PublicationError): complete_execution(ex)
    with pytest.raises(PublicationError): TrainingCompletion(c.run_digest,c.final_state_digest,c.receipt_digests,c.seed,c.tokens,c.compute_units,"production")

def test_mirror_parity():
    from pathlib import Path
    root=Path(__file__).parents[2]
    assert (root/"skeleton/modeling/publication.py").read_bytes()==(root/"skeleton/ai/modeling/publication.py").read_bytes()
