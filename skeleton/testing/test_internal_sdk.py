import pytest
from skeleton.ai.internal_sdk import *
def test_supported_boundary_resolves():
 sdk = InternalSDK(SDKCompatibility("v1",(SDKExport("clock","skeleton.sdk.clock","v1"),)))
 assert sdk.resolve("clock") == "skeleton.sdk.clock"

def test_unknown_or_private_surface_rejected():
 sdk=InternalSDK(SDKCompatibility("v1",()))
 with pytest.raises(ImportError):sdk.resolve("internal.deep")
 with pytest.raises(ImportError):InternalSDK(SDKCompatibility("v1",(SDKExport("_x","skeleton._private","v1"),))).resolve("_x")

def test_internal_deep_target_outside_sdk_surface_rejected():
 import pytest
 s=InternalSDK(SDKCompatibility("v1",(SDKExport("x","skeleton.internal.deep","v1"),)))
 with pytest.raises(ImportError):s.resolve("x")


def test_explicit_foundation_target_cannot_bypass_sdk_namespace():
 sdk = InternalSDK(SDKCompatibility("v1",(SDKExport("clock","skeleton.foundation.time","v1"),)))
 with pytest.raises(ImportError, match="deep/private"):
  sdk.resolve("clock")
