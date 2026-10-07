import pytest
from skeleton.automation.build_replay import replay_key,reject_seen
def test_replay_is_authority_bound():
 assert replay_key(head_sha="a",generation="g",allocation="x",task="t")!=replay_key(head_sha="b",generation="g",allocation="x",task="t")
def test_seen_rejected():
 with pytest.raises(ValueError):reject_seen("x",{"x"})
