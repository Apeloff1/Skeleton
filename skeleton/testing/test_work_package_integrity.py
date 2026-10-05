from __future__ import annotations
import hashlib,pytest
from skeleton.automation.work_packages import *
SHA=hashlib.sha256(b"x").hexdigest()
def pkg(i="PKG.095"):return WorkPackage(i,"VOL.095","Build exact package",("Do not merge",),("API.X",),("OWNER.X",),("RISK.X",),("TEST.X",),"Rollback commit",("REQ.1",),("AIQ.1",))
def ev(i,role,actor,p="PKG.095"):return WorkPackageEvidence(i,p,role,actor,SHA)
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
