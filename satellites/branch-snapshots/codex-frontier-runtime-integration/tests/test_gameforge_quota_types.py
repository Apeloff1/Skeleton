import pytest

from skeleton.frontier.gameforge_quota import Quota


def test_quota_rejects_boolean_limit():
    with pytest.raises(ValueError):
        Quota(True)


def test_quota_rejects_boolean_amounts():
    quota = Quota(2)
    with pytest.raises(ValueError):
        quota.reserve(True)
    with pytest.raises(ValueError):
        quota.release(True)


def test_quota_respects_limit():
    quota = Quota(2)
    assert quota.reserve(2)
    assert quota.exhausted
    assert not quota.reserve(1)
