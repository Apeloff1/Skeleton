import pytest
from skeleton.automation.studio_artifact_custody import ArtifactCustody
def test_custody_roundtrip():
 c=ArtifactCustody.from_bytes("patch",b"abc"); c.verify(b"abc")
def test_custody_detects_mutation():
 c=ArtifactCustody.from_bytes("patch",b"abc")
 with pytest.raises(ValueError): c.verify(b"abd")
