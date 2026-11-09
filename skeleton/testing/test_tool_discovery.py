from skeleton.ai.tool_discovery import *
def att():return ManifestAttestation("root","digest",True)
def test_boolean_signed_assertion_is_not_trust_evidence():assert not validate_manifest(ToolManifest("t",(ToolCapability("x","s"),),True),{"x"}).validated
def test_trusted_attestation_validates_known_capability():assert validate_manifest(ToolManifest("t",(ToolCapability("x","s"),),attestation=att()),{"x"}).validated
def test_discovery_never_grants_authority():assert not validate_manifest(ToolManifest("t",(ToolCapability("x","s"),),attestation=att()),{"x"}).granted_authority
def test_duplicate_capability_rejected():assert not validate_manifest(ToolManifest("t",(ToolCapability("x","s"),ToolCapability("x","s")),attestation=att()),{"x"}).validated
