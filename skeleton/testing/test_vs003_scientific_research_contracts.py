from __future__ import annotations
import hashlib,pytest
from skeleton.ai.research import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
def node(i="EVID.1",out=Outcome.SUPPORTS): return EvidenceNode(i,"SOURCE.1",S("source"),"controlled benchmark",("CLAIM.1",),out)
def test_question_requires_scope_and_limitations():
 with pytest.raises(ResearchError): ResearchQuestion("QUESTION.1","q","scope",())
def test_evidence_identity_is_immutable():
 g=EvidenceGraph();g.add(node())
 with pytest.raises(ResearchError,match="immutable"):g.add(node(out=Outcome.NEGATIVE))
def test_experiment_requires_preregistered_metrics_and_bounded_trials():
 with pytest.raises(ResearchError):ExperimentPlan("EXP.1","h",(),"rule",10)
 with pytest.raises(ResearchError):ExperimentPlan("EXP.1","h",("METRIC.1",),"rule",10001)
def test_reproduction_rejects_nonfinite_metric():
 p=ExperimentPlan("EXP.1","h",("METRIC.1",),"rule",2)
 with pytest.raises(ValueError):ReproductionRecord("REPRO.1",S("e"),p.digest,(("METRIC.1",float("nan")),),Outcome.AMBIGUOUS,1)
def test_negative_evidence_must_be_disclosed():
 n=node(out=Outcome.NEGATIVE)
 with pytest.raises(ResearchError,match="disclose"):ResearchConclusion("CONCLUSION.1","QUESTION.1","CLAIM.1",(n.digest,),(n.outcome,),"claim",("small_sample",))
def test_negative_evidence_can_be_preserved_explicitly():
 n=node(out=Outcome.NEGATIVE);c=ResearchConclusion("CONCLUSION.1","QUESTION.1","CLAIM.1",(n.digest,),(n.outcome,),"not supported",("conflicting_or_negative_evidence",));assert c.outcomes==(Outcome.NEGATIVE,)
def test_claim_graph_returns_only_bound_evidence():
 g=EvidenceGraph();g.add(node("EVID.2"));g.add(EvidenceNode("EVID.1","SOURCE.2",S("s2"),"replication",("CLAIM.2",),Outcome.SUPPORTS));assert [n.evidence_id for n in g.for_claim("CLAIM.1")]==["EVID.2"]

def test_runtime_outcome_and_trial_types_fail_closed():
 with pytest.raises(ResearchError,match="Outcome"):EvidenceNode("EVID.X","SOURCE.X",S("s"),"method",("CLAIM.1",),"supports")
 p=ExperimentPlan("EXP.1","h",("METRIC.1",),"rule",2)
 with pytest.raises(ResearchError,match="positive integer"):ReproductionRecord("REPRO.X",S("e"),p.digest,(("METRIC.1",1.0),),Outcome.SUPPORTS,True)
def test_duplicate_reproduction_metrics_are_rejected():
 p=ExperimentPlan("EXP.1","h",("METRIC.1",),"rule",2)
 with pytest.raises(ResearchError,match="duplicate"):ReproductionRecord("REPRO.X",S("e"),p.digest,(("METRIC.1",1.0),("METRIC.1",2.0)),Outcome.AMBIGUOUS,1)
def test_reproduction_must_match_exact_evidence_experiment_and_metrics():
 n=node();p=ExperimentPlan("EXP.1","h",("METRIC.1",),"rule",2)
 r=ReproductionRecord("REPRO.1",n.digest,p.digest,(("METRIC.1",1.0),),Outcome.SUPPORTS,2)
 validate_reproduction(n,p,r);assert len(r.digest)==64
 with pytest.raises(ResearchError,match="stale or bound"):validate_reproduction(node("EVID.2"),p,r)
 p2=ExperimentPlan("EXP.2","h",("METRIC.1",),"rule",2)
 with pytest.raises(ResearchError,match="stale or bound"):validate_reproduction(n,p2,r)
def test_reproduction_cannot_exceed_preregistered_trials_or_change_metrics():
 n=node();p=ExperimentPlan("EXP.1","h",("METRIC.1",),"rule",1)
 over=ReproductionRecord("REPRO.1",n.digest,p.digest,(("METRIC.1",1.0),),Outcome.SUPPORTS,2)
 with pytest.raises(ResearchError,match="trial budget"):validate_reproduction(n,p,over)
 wrong=ReproductionRecord("REPRO.2",n.digest,p.digest,(("METRIC.2",1.0),),Outcome.SUPPORTS,1)
 with pytest.raises(ResearchError,match="preregistration"):validate_reproduction(n,p,wrong)

def test_synthesis_uses_complete_claim_graph_and_preserves_conflict():
 q=ResearchQuestion("QUESTION.1","does it work?","bounded claim",("small corpus",));g=EvidenceGraph()
 a=node("EVID.1",Outcome.SUPPORTS);b=node("EVID.2",Outcome.CONTRADICTS);g.add(a);g.add(b)
 c=synthesize(q,"CLAIM.1",g,"mixed result",("small corpus",))
 assert c.evidence_digests==(a.digest,b.digest)
 assert c.outcomes==(Outcome.SUPPORTS,Outcome.CONTRADICTS)
 assert "conflicting_or_negative_evidence" in c.limitations
def test_synthesis_rejects_claim_without_evidence():
 q=ResearchQuestion("QUESTION.1","q","scope",("limit",))
 with pytest.raises(ResearchError,match="unsupported claim"):synthesize(q,"CLAIM.1",EvidenceGraph(),"claim",("limit",))
