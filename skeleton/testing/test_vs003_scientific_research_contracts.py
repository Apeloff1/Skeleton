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
