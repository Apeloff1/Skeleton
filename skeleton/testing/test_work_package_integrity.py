from __future__ import annotations
import hashlib,pytest
from datetime import datetime,timezone,timedelta
from skeleton.automation.work_packages import *
SHA=hashlib.sha256(b"x").hexdigest()
NOW=datetime(2026,10,5,14,0,tzinfo=timezone.utc)
def pkg(i="PKG.095"):return WorkPackage(i,"VOL.095","Build exact package",("Do not merge",),("API.X",),("OWNER.X",),("RISK.X",),("TEST.X",),"Rollback commit",("REQ.1",),("AIQ.1",))
def ev(i,role,actor,p="PKG.095",package=None,digest=None,observed_at=NOW):
 target=package or pkg(p)
 return WorkPackageEvidence(i,p,digest or target.digest,role,actor,SHA,observed_at)
def test_package_requires_all_structural_fields():
 with pytest.raises(WorkPackageError,match="tests"):WorkPackage("PKG.X","VOL.095","x",("n",),("i",),("o",),("r",),(),"rb",("q",),("a",))
def test_state_is_derived_not_manually_set():
 r=WorkPackageRegistry();r.add(pkg());assert r.state("PKG.095") is PackageState.READY
 r.attest(ev("EVID.I",EvidenceRole.IMPLEMENTATION,"ACTOR.BUILD"));assert r.state("PKG.095") is PackageState.IMPLEMENTED
 r.attest(ev("EVID.V",EvidenceRole.VERIFICATION,"ACTOR.VERIFY"));assert r.state("PKG.095") is PackageState.VERIFIED
 r.attest(ev("EVID.C",EvidenceRole.COMPLETION,"ACTOR.SIGN"));assert r.state("PKG.095") is PackageState.COMPLETE
def test_self_verification_rejected():
 r=WorkPackageRegistry();r.add(pkg());r.attest(ev("EVID.I",EvidenceRole.IMPLEMENTATION,"ACTOR.X"));r.attest(ev("EVID.V",EvidenceRole.VERIFICATION,"ACTOR.X"))
 with pytest.raises(WorkPackageError,match="independent"):r.state("PKG.095")
def test_completion_cannot_be_implementation_actor():
 r=WorkPackageRegistry();r.add(pkg());r.attest(ev("EVID.I",EvidenceRole.IMPLEMENTATION,"ACTOR.X"));r.attest(ev("EVID.V",EvidenceRole.VERIFICATION,"ACTOR.Y"));r.attest(ev("EVID.C",EvidenceRole.COMPLETION,"ACTOR.X"))
 with pytest.raises(WorkPackageError,match="completion signer"):r.state("PKG.095")
def test_dependency_blocks_until_exact_upstream_completion():
 r=WorkPackageRegistry();r.add(pkg("PKG.A"));r.add(pkg("PKG.B"));r.depend(WorkPackageDependency("DEP.BA","PKG.B","PKG.A"));assert r.state("PKG.B") is PackageState.BLOCKED
def test_cycle_rejected():
 r=WorkPackageRegistry();r.add(pkg("PKG.A"));r.add(pkg("PKG.B"));r.depend(WorkPackageDependency("DEP.AB","PKG.A","PKG.B"))
 with pytest.raises(WorkPackageError,match="cycle"):r.depend(WorkPackageDependency("DEP.BA","PKG.B","PKG.A"))
def test_package_identity_immutable():
 r=WorkPackageRegistry();r.add(pkg())
 with pytest.raises(WorkPackageError,match="immutable"):r.add(WorkPackage("PKG.095","VOL.095","changed",("n",),("i",),("o",),("r",),("t",),"rb",("q",),("a",)))

def test_evidence_is_bound_to_exact_package_digest():
 r=WorkPackageRegistry();p=pkg();r.add(p)
 with pytest.raises(WorkPackageError,match="stale or bound"):
  r.attest(ev("EVID.I",EvidenceRole.IMPLEMENTATION,"ACTOR.X",package=p,digest=hashlib.sha256(b"old").hexdigest()))

def test_evidence_role_must_be_typed():
 p=pkg()
 with pytest.raises(WorkPackageError,match="EvidenceRole"):
  WorkPackageEvidence("EVID.X",p.package_id,p.digest,"implementation","ACTOR.X",SHA)

def test_dependency_identity_is_immutable():
 r=WorkPackageRegistry();r.add(pkg("PKG.A"));r.add(pkg("PKG.B"));r.add(pkg("PKG.C"))
 r.depend(WorkPackageDependency("DEP.X","PKG.B","PKG.A"))
 with pytest.raises(WorkPackageError,match="dependency identity immutable"):
  r.depend(WorkPackageDependency("DEP.X","PKG.C","PKG.A"))

def test_structural_collections_are_typed_and_bounded():
 with pytest.raises(WorkPackageError,match="non_goals must be tuple"):
  WorkPackage("PKG.X","VOL.095","x",["n"],("i",),("o",),("r",),("t",),"rb",("q",),("a",))

def test_completion_signer_cannot_be_verification_actor():
 r=WorkPackageRegistry();p=pkg();r.add(p)
 r.attest(ev("EVID.I",EvidenceRole.IMPLEMENTATION,"ACTOR.I",package=p))
 r.attest(ev("EVID.V",EvidenceRole.VERIFICATION,"ACTOR.V",package=p))
 r.attest(ev("EVID.C",EvidenceRole.COMPLETION,"ACTOR.V",package=p))
 with pytest.raises(WorkPackageError,match="verification actor"):r.state(p.package_id)

def test_actor_cannot_contradict_same_role_evidence():
 r=WorkPackageRegistry();p=pkg();r.add(p)
 r.attest(ev("EVID.I1",EvidenceRole.IMPLEMENTATION,"ACTOR.I",package=p))
 with pytest.raises(WorkPackageError,match="contradict evidence"):
  r.attest(WorkPackageEvidence("EVID.I2",p.package_id,p.digest,EvidenceRole.IMPLEMENTATION,"ACTOR.I",hashlib.sha256(b"other").hexdigest(),NOW))

def test_stale_package_evidence_is_rejected():
 r=WorkPackageRegistry();p=pkg();r.add(p)
 stale=WorkPackage("PKG.095","VOL.095","old objective",p.non_goals,p.interfaces,p.state_owners,p.risks,p.tests,p.rollback,p.requirement_ids,p.aiq_task_ids)
 with pytest.raises(WorkPackageError,match="stale or bound"):r.attest(ev("EVID.STALE",EvidenceRole.IMPLEMENTATION,"ACTOR.X",package=stale))

def test_evidence_role_and_timestamp_are_typed():
 p=pkg()
 with pytest.raises(WorkPackageError,match="EvidenceRole"):WorkPackageEvidence("EVID.X",p.package_id,p.digest,"implementation","ACTOR.X",SHA,NOW)
 with pytest.raises(WorkPackageError,match="timezone-aware"):WorkPackageEvidence("EVID.X",p.package_id,p.digest,EvidenceRole.IMPLEMENTATION,"ACTOR.X",SHA,datetime(2026,10,5))

def test_package_collections_are_typed_and_bounded():
 p=pkg()
 with pytest.raises(WorkPackageError,match="must be tuple"):WorkPackage(p.package_id,p.volume_id,p.objective,list(p.non_goals),p.interfaces,p.state_owners,p.risks,p.tests,p.rollback,p.requirement_ids,p.aiq_task_ids)
 with pytest.raises(WorkPackageError,match="exceeds policy bound"):WorkPackage("PKG.BIG","VOL.095","x",tuple(f"NG.{i}" for i in range(257)),("I",),("O",),("R",),("T",),"rb",("Q",),("A",))

def test_dependency_identity_is_immutable():
 r=WorkPackageRegistry();r.add(pkg("PKG.A"));r.add(pkg("PKG.B"));r.add(pkg("PKG.C"))
 r.depend(WorkPackageDependency("DEP.X","PKG.B","PKG.A"))
 with pytest.raises(WorkPackageError,match="dependency identity"):r.depend(WorkPackageDependency("DEP.X","PKG.C","PKG.A"))

def test_completion_signer_must_be_independent_from_verifier():
 r=WorkPackageRegistry();p=pkg();r.add(p)
 r.attest(ev("EVID.I",EvidenceRole.IMPLEMENTATION,"ACTOR.I",package=p))
 r.attest(ev("EVID.V",EvidenceRole.VERIFICATION,"ACTOR.V",package=p))
 r.attest(ev("EVID.C",EvidenceRole.COMPLETION,"ACTOR.V",package=p))
 with pytest.raises(WorkPackageError,match="verification actor"):r.state(p.package_id)

def test_evidence_rollup_is_deterministic_and_exact_version_bound():
 r=WorkPackageRegistry();p=pkg();r.add(p)
 r.attest(ev("EVID.I",EvidenceRole.IMPLEMENTATION,"ACTOR.I",package=p))
 roll=r.evidence_rollup(p.package_id)
 assert roll["package_digest"]==p.digest
 assert roll["state"]==PackageState.IMPLEMENTED.value
 assert roll["evidence_ids"]==("EVID.I",)
 assert roll["artifact_digests"]==(SHA,)
 assert roll["observed_at_utc"]==(NOW.isoformat(),)

def test_evidence_timestamp_normalizes_to_utc_and_rejects_fractional_seconds():
 p=pkg()
 offset=datetime(2026,10,5,16,0,tzinfo=timezone(timedelta(hours=2)))
 e=WorkPackageEvidence("EVID.UTC",p.package_id,p.digest,EvidenceRole.IMPLEMENTATION,"ACTOR.I",SHA,offset)
 assert e.observed_at==NOW
 with pytest.raises(WorkPackageError,match="whole-second precision"):
  WorkPackageEvidence("EVID.SUB",p.package_id,p.digest,EvidenceRole.IMPLEMENTATION,"ACTOR.I",SHA,NOW.replace(microsecond=1))

def test_failed_dependency_cycle_is_transactional():
 r=WorkPackageRegistry();r.add(pkg("PKG.A"));r.add(pkg("PKG.B"))
 r.depend(WorkPackageDependency("DEP.AB","PKG.A","PKG.B"))
 with pytest.raises(WorkPackageError,match="cycle"):r.depend(WorkPackageDependency("DEP.BA","PKG.B","PKG.A"))
 assert "DEP.BA" not in r.dependencies
 assert r.state("PKG.A") is PackageState.BLOCKED
 assert r.state("PKG.B") is PackageState.READY

def test_duplicate_dependency_edge_is_rejected():
 r=WorkPackageRegistry();r.add(pkg("PKG.A"));r.add(pkg("PKG.B"))
 r.depend(WorkPackageDependency("DEP.1","PKG.B","PKG.A"))
 with pytest.raises(WorkPackageError,match="duplicate dependency edge"):
  r.depend(WorkPackageDependency("DEP.2","PKG.B","PKG.A"))

def test_structural_collections_are_canonical_and_do_not_silently_deduplicate():
 p=WorkPackage("PKG.CAN","VOL.095"," x ",(" non-goal ",),(" API.X ",),(" OWNER.X ",),(" RISK.X ",),(" TEST.X ",)," rb ",("REQ.1",),("AIQ.1",))
 assert p.objective=="x"
 assert p.non_goals==("non-goal",)
 assert p.interfaces==("API.X",)
 with pytest.raises(WorkPackageError,match="duplicate values"):
  WorkPackage("PKG.DUP","VOL.095","x",("same"," same "),("I",),("O",),("R",),("T",),"rb",("REQ.1",),("AIQ.1",))

def test_requirement_and_aiq_references_require_stable_ids():
 with pytest.raises(WorkPackageError,match="stable identifier"):
  WorkPackage("PKG.BAD","VOL.095","x",("n",),("i",),("o",),("r",),("t",),"rb",("free text",),("AIQ.1",))

def test_newer_implementation_invalidates_older_verification():
 r=WorkPackageRegistry();p=pkg();r.add(p)
 r.attest(ev("EVID.I1",EvidenceRole.IMPLEMENTATION,"ACTOR.I",package=p,observed_at=NOW))
 r.attest(ev("EVID.V1",EvidenceRole.VERIFICATION,"ACTOR.V",package=p,observed_at=NOW+timedelta(seconds=1)))
 assert r.state(p.package_id) is PackageState.VERIFIED
 r.attest(ev("EVID.I2",EvidenceRole.IMPLEMENTATION,"ACTOR.I2",package=p,observed_at=NOW+timedelta(seconds=2)))
 assert r.state(p.package_id) is PackageState.IMPLEMENTED

def test_newer_verification_invalidates_older_completion():
 r=WorkPackageRegistry();p=pkg();r.add(p)
 r.attest(ev("EVID.I",EvidenceRole.IMPLEMENTATION,"ACTOR.I",package=p,observed_at=NOW))
 r.attest(ev("EVID.V1",EvidenceRole.VERIFICATION,"ACTOR.V1",package=p,observed_at=NOW+timedelta(seconds=1)))
 r.attest(ev("EVID.C",EvidenceRole.COMPLETION,"ACTOR.C",package=p,observed_at=NOW+timedelta(seconds=2)))
 assert r.state(p.package_id) is PackageState.COMPLETE
 r.attest(ev("EVID.V2",EvidenceRole.VERIFICATION,"ACTOR.V2",package=p,observed_at=NOW+timedelta(seconds=3)))
 assert r.state(p.package_id) is PackageState.VERIFIED
