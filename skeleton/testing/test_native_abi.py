from __future__ import annotations
import pytest
from skeleton.native.protocol import AcceleratorProtocolError,ProtocolVersion,negotiate_version

def test_protocol_negotiation_selects_highest_exact_shared_version():
 assert negotiate_version((ProtocolVersion(1,0),ProtocolVersion(1,2)),(ProtocolVersion(1,1),ProtocolVersion(1,2)))==ProtocolVersion(1,2)

def test_protocol_negotiation_fails_closed_across_unshared_abi_versions():
 with pytest.raises(AcceleratorProtocolError,match="no compatible"):
  negotiate_version((ProtocolVersion(1,0),),(ProtocolVersion(2,0),))

def test_protocol_version_rejects_boolean_numeric_aliases():
 with pytest.raises(ValueError):ProtocolVersion(True,0)
