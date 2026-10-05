from skeleton.ai.tool_discovery import *
def test_unsigned_or_unknown_manifest_is_untrusted():assert not validate_manifest(ToolManifest("t",(ToolCapability("x","s"),),False),{"x"}).validated
def test_discovery_never_grants_authority():assert not validate_manifest(ToolManifest("t",(ToolCapability("x","s"),),True),{"x"}).granted_authority
