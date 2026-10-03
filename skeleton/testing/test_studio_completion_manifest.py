import pytest
from skeleton.automation.studio_completion_manifest import CompletionManifest
def test_manifest_digest_stable():
 m=CompletionManifest("r","a"*40,"g",("t",),"b"*64,("c"*64,))
 m.validate(); assert m.digest()==m.digest()
def test_manifest_requires_identity():
 with pytest.raises(ValueError): CompletionManifest("","a"*40,"g",(),"b"*64,()).validate()
