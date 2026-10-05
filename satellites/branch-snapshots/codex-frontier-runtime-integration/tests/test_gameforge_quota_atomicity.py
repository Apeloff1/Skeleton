import pytest

from skeleton.frontier.gameforge_quota import Quota


def test_quota_rejects_boolean_amounts():
    quota = Quota(2)
    with pytest.raises(ValueError):
        quota.reserve(True)
    with pytest.raises(ValueError):
        quota.release(True)


def test_quota_cannot_release_more_than_reserved():
    quota = Quota(2)
    assert quota.reserve(2)
    with pytest.raises(ValueError):
        quota.release(3)
    assert quota.used == 2
    assert quota.remaining == 0
