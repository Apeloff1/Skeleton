from __future__ import annotations
import hashlib,pytest
from skeleton.eval.functional_acceptance import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
def evidence(fail=None):
 return tuple(AcceptanceEvidence("EVID."+c.name,c,S(c.value),c is not fail,("observed-negative",) if c is fail else ()) for c in Criterion)
def bundle(ev=None):return FunctionalAIAcceptance("ACCEPT.VOL104",S("source"),S("config"),S("model"),S("env"),ev or evidence(),"ACTOR.BUILDER")
def test_complete_matrix_is_eligible():
 assert bundle().eligible
def test_missing_failure_evidence_rejected():
 ev=tuple(x for x in evidence() if x.criterion is not Criterion.FAILURE)
 with pytest.raises(AcceptanceError,match="incomplete"):bundle(ev)
def test_failed_negative_evidence_blocks_acceptance_without_being_erased():
 b=bundle(evidence(Criterion.SECURITY));assert not b.eligible;assert next(x for x in b.evidence if x.criterion is Criterion.SECURITY).negative_findings
 with pytest.raises(AcceptanceError,match="failed criterion"):sign(b,"ACTOR.REVIEWER")
def test_self_signoff_rejected():
 with pytest.raises(AcceptanceError,match="independent"):sign(bundle(),"ACTOR.BUILDER")
def test_signoff_binds_exact_source_config_model_environment_bundle():
 b=bundle();s=sign(b,"ACTOR.REVIEWER");assert s.acceptance_digest==b.digest
def test_duplicate_evidence_identity_rejected():
 ev=list(evidence());ev[-1]=AcceptanceEvidence(ev[0].evidence_id,ev[-1].criterion,ev[-1].artifact_digest,True)
 with pytest.raises(AcceptanceError,match="duplicate"):bundle(tuple(ev))

def test_evidence_runtime_types_fail_closed():
 with pytest.raises(AcceptanceError,match="criterion must be Criterion"):AcceptanceEvidence("EVID.X","security",S("x"),True)
 with pytest.raises(AcceptanceError,match="passed must be bool"):AcceptanceEvidence("EVID.X",Criterion.SECURITY,S("x"),1)
 with pytest.raises(AcceptanceError,match="bounded tuple"):AcceptanceEvidence("EVID.X",Criterion.SECURITY,S("x"),True,["bad"])
def test_signoff_approval_is_strict_boolean():
 b=bundle()
 with pytest.raises(AcceptanceError,match="approved must be bool"):AcceptanceSignoff(b.digest,"ACTOR.REVIEWER",b.builder_id,1)
def test_acceptance_evidence_collection_must_be_typed_tuple():
 with pytest.raises(AcceptanceError,match="typed tuple"):FunctionalAIAcceptance("ACCEPT.X",S("s"),S("c"),S("m"),S("e"),list(evidence()),"ACTOR.BUILDER")
