import pytest
from skeleton.frontier.gameforge_quota import Quota

def test_quota_bounds_usage():
 q=Quota(2); assert q.reserve(); assert not q.reserve(2); q.release(); assert q.reserve(2)

def test_quota_rejects_invalid_amounts():
 with pytest.raises(ValueError): Quota(0)
