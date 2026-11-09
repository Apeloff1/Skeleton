import pytest
from skeleton.modeling import *
from skeleton.modeling.evaluation import EvaluationEvidence,PromotionEligibility,EvaluationError,assess_eligibility
H="a"*64
def fixtures():
    reg=ModelDevelopmentRegistry(); ds=DatasetManifest("ds",H,"owned",H,"none","b"*64,"c"*64,("src",)); dd=reg.add_dataset(ds)
    run=TrainingRun("run",(dd,),H,"b"*64,"c"*64,3,status="completed"); reg.add_run(run)
    ex=TrainingExecution(run.run_digest,TrainingBudget(1,5,5),3); ex.record_step(StepReceipt(run.run_digest,1,H,"d"*64,1,1))
    c=complete_execution(ex); a=ModelArtifact("m","e"*64,run.run_digest,"f"*64,"weights")
    return a,c
def test_exact_evidence_can_establish_eligibility_not_authority():
    a,c=fixtures(); e=EvaluationEvidence(a.artifact_digest,c.completion_digest,a.evaluation_digest,{"accuracy":.9},True)
    x=assess_eligibility(a,c,e); assert x.eligible and x.authority_scope=="eligibility-only"
def test_failed_evaluation_is_deterministically_ineligible():
    a,c=fixtures(); e=EvaluationEvidence(a.artifact_digest,c.completion_digest,a.evaluation_digest,{},False)
    assert not assess_eligibility(a,c,e).eligible
@pytest.mark.parametrize("field",["artifact","completion","suite"])
def test_cross_identity_evidence_fails_closed(field):
    a,c=fixtures(); kw=dict(artifact_digest=a.artifact_digest,completion_digest=c.completion_digest,suite_digest=a.evaluation_digest,passed=True)
    kw[{"artifact":"artifact_digest","completion":"completion_digest","suite":"suite_digest"}[field]]="0"*64
    with pytest.raises(EvaluationError): assess_eligibility(a,c,EvaluationEvidence(**kw))
def test_nonfinite_metrics_and_authority_escalation_denied():
    a,c=fixtures()
    with pytest.raises(EvaluationError): EvaluationEvidence(a.artifact_digest,c.completion_digest,a.evaluation_digest,{"loss":float("nan")},True)
    with pytest.raises(EvaluationError): EvaluationEvidence(a.artifact_digest,c.completion_digest,a.evaluation_digest,{},True,"production")
def test_evidence_identity_is_order_deterministic_and_immutable():
    a,c=fixtures(); x=EvaluationEvidence(a.artifact_digest,c.completion_digest,a.evaluation_digest,{"b":2,"a":1},True); y=EvaluationEvidence(a.artifact_digest,c.completion_digest,a.evaluation_digest,{"a":1,"b":2},True)
    assert x.evidence_digest==y.evidence_digest
    with pytest.raises(TypeError): x.metrics["a"]=9
def test_mirror_parity():
    from pathlib import Path
    root=Path(__file__).parents[2]; assert (root/"skeleton/modeling/evaluation.py").read_bytes()==(root/"skeleton/ai/modeling/evaluation.py").read_bytes()
