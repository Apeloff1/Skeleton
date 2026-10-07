import pytest
from skeleton.automation.build_certificate import BuildCertificate
def test_complete_certificate():
 c=BuildCertificate("id","a"*40,"b"*40,3,2,("c"*64,),"complete"); assert len(c.digest())==64
def test_incomplete_not_certified():
 with pytest.raises(ValueError): BuildCertificate("id","a"*40,"b"*40,1,0,(),"continue").digest()
