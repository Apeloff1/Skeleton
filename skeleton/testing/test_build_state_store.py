import pytest
from skeleton.automation.build_state_store import advance,StateEnvelope
def test_state_revision_monotonic():
 a=advance(None,head_sha="a"*40,payload={"x":1});b=advance(a,head_sha="b"*40,payload={"x":2});assert b.revision==1;b.verify()
def test_tamper_rejected():
 a=advance(None,head_sha="a"*40,payload={"x":1})
 with pytest.raises(ValueError):StateEnvelope(a.revision,a.head_sha,{"x":2},a.sha256).verify()
