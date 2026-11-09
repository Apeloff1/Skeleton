import pytest
from skeleton.automation.build_completion_proof import CompletionProof
def test_proof_digest():
 p=CompletionProof("a"*40,"b"*64,"c"*64,"d"*64,"e"*64,("f"*64,));assert len(p.digest())==64
def test_bad_digest_rejected():
 with pytest.raises(ValueError):CompletionProof("a"*40,"bad","c"*64,"d"*64,"e"*64,()).validate()
