from __future__ import annotations
import hashlib,pytest
from skeleton.app.final_assembly import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
def plan():return FinalAssemblyPlan("ASSEMBLY.120","AUTHORITY.RELEASE",S("head"),S("env"),S("artifact"),("GATE.FAILURE","GATE.RESTORE","GATE.ROLLBACK"))
def run(**kw):
 v=dict(plan_id="ASSEMBLY.120",authority_id="AUTHORITY.RELEASE",head_digest=S("head"),environment_digest=S("env"),artifact_digest=S("artifact"),passed_gate_ids=("GATE.FAILURE","GATE.RESTORE","GATE.ROLLBACK"),evidence_digest=S("evidence"));v.update(kw);return FinalAssemblyRun(**v)
def evidence(**kw):
 v=dict(run=run(),independent_verifier_id="VERIFIER.2",verified_evidence_digest=S("evidence"),unresolved_risk_ids=());v.update(kw);return FinalAssemblyEvidence(**v)
def test_exact_head_environment_artifact_and_gates_are_noncompensable():
 with pytest.raises(FinalAssemblyError,match="exact plan"):qualify(plan(),evidence(run=run(head_digest=S("other"))))
 with pytest.raises(FinalAssemblyError,match="exact assembly gates"):qualify(plan(),evidence(run=run(passed_gate_ids=("GATE.FAILURE","GATE.RESTORE"))))
def test_unresolved_risk_blocks_release_even_after_all_gates_pass():
 with pytest.raises(FinalAssemblyError,match="risks block"):qualify(plan(),evidence(unresolved_risk_ids=("RISK.ENV",)))
def test_independent_verification_cannot_be_fabricated_or_digest_shifted():
 with pytest.raises(FinalAssemblyError,match="independent verification"):qualify(plan(),evidence(independent_verifier_id=None,verified_evidence_digest=None))
 with pytest.raises(FinalAssemblyError,match="digest mismatch"):qualify(plan(),evidence(verified_evidence_digest=S("other")))
def test_valid_exact_evidence_returns_only_verified_digest():assert qualify(plan(),evidence())==S("evidence")

def test_verifier_must_be_independent_from_assembly_authority():
 with pytest.raises(FinalAssemblyError,match="independent from assembly authority"):qualify(plan(),evidence(independent_verifier_id="AUTHORITY.RELEASE"))
def test_run_cannot_substitute_release_authority():
 with pytest.raises(FinalAssemblyError,match="exact plan"):qualify(plan(),evidence(run=run(authority_id="AUTHORITY.OTHER")))

def test_authoritative_collections_are_bounded():
 with pytest.raises(FinalAssemblyError,match="gate count exceeds"):FinalAssemblyPlan("ASSEMBLY.120","AUTHORITY.RELEASE",S("head"),S("env"),S("artifact"),tuple(f"GATE.{i}" for i in range(513)))
 with pytest.raises(FinalAssemblyError,match="passed gate count exceeds"):run(passed_gate_ids=tuple(f"GATE.{i}" for i in range(513)))
 with pytest.raises(FinalAssemblyError,match="risk count exceeds"):evidence(unresolved_risk_ids=tuple(f"RISK.{i}" for i in range(4097)))
