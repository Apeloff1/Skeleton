import pytest
from skeleton.ai.runtime.deferred.recovery_diagnostics import *
D="a"*64
def test_recovery_handoff_requires_fewer_dependencies_and_valid_artifacts():
 a=RecoveryArtifact("a",D,D,True); assert validate_recovery(BootstrapRecovery("r",(a,),1),5).handoff_allowed
 assert not validate_recovery(BootstrapRecovery("r",(a,),5),5).handoff_allowed
def test_recovery_rejects_corrupt_or_unsigned_artifact():
 for a in (RecoveryArtifact("a",D,"b"*64,True),RecoveryArtifact("a",D,D,False)):
  assert not validate_recovery(BootstrapRecovery("r",(a,),1),5).handoff_allowed
def test_crash_report_must_be_redacted_even_when_telemetry_failed():
 with pytest.raises(ValueError): CrashReport(CrashContext("x","c",()),CrashSignature("E",D),False,False)
 assert CrashReport(CrashContext("x","c",()),CrashSignature("E",D),False,True).identity
def test_support_bundle_rejects_non_allowlisted_path():
 m=SupportManifest(("safe.txt",),(("safe.txt",sha256_json({"content":"ok"})),),"tomorrow")
 with pytest.raises(ValueError): SupportBundle(m,(("secret.env","x"),),SupportRedaction(()))
def test_support_bundle_validates_manifest_digest():
 m=SupportManifest(("safe.txt",),(("safe.txt",D),),"tomorrow")
 with pytest.raises(ValueError,match="digest"): SupportBundle(m,(("safe.txt","changed"),),SupportRedaction(()))
def test_support_bundle_rejects_declared_secret():
 c="token=SECRET"; m=SupportManifest(("x",),(("x",sha256_json({"content":c})),),"tomorrow")
 with pytest.raises(ValueError,match="secret"): SupportBundle(m,(("x",c),),SupportRedaction(("SECRET",)))
def test_doctor_report_diagnoses_without_implicitly_repairing():
 f=DoctorFinding(DoctorCheck("c","db"),FindingState.BROKEN,D,"restore")
 assert not DoctorReport((f,)).healthy
 with pytest.raises(ValueError,match="authorization"): RepairRequest(f,"")
def test_doctor_health_requires_findings_and_all_healthy():
 assert not DoctorReport(()).healthy
 f=DoctorFinding(DoctorCheck("c","db"),FindingState.HEALTHY,D,"none")
 assert DoctorReport((f,)).healthy
def test_self_diagnosis_cannot_self_certify_production_health():
 e=HealthEvidence("db",FindingState.HEALTHY,FindingState.HEALTHY,D); d=SelfDiagnostic((e,),())
 assert d.advisory_health is FindingState.HEALTHY and not d.production_certified
def test_self_diagnosis_is_unknown_without_external_evidence():
 e=HealthEvidence("db",FindingState.HEALTHY,None,D)
 assert SelfDiagnostic((e,),()).advisory_health is FindingState.UNKNOWN
def test_fault_hypothesis_confidence_is_bounded():
 with pytest.raises(ValueError): FaultHypothesis("db","maybe",D,1.1)
