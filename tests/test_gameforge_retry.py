import pytest
from skeleton.frontier.gameforge_retry import RetryPolicy

def test_retry_backoff_is_bounded():
    p=RetryPolicy(3,.25,1.0); assert [p.delay(i) for i in range(5)]==[.25,.5,1.0,1.0,1.0]

def test_retry_policy_rejects_invalid_values():
    with pytest.raises(ValueError): RetryPolicy(0)
    with pytest.raises(ValueError): RetryPolicy(3,1,0)
    with pytest.raises(ValueError): RetryPolicy().delay(-1)
