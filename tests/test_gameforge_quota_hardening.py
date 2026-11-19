import pytest

from skeleton.frontier.gameforge_quota import Quota


def test_quota_remaining_and_exhaustion():
    quota = Quota(2)
    assert quota.remaining == 2
    assert not quota.exhausted
    assert quota.reserve(2)
    assert quota.remaining == 0
    assert quota.exhausted


def test_quota_rejects_non_integer_amounts():
    quota = Quota(2)
    with pytest.raises(ValueError):
        quota.reserve(1.5)
    with pytest.raises(ValueError):
        quota.release(1.5)
