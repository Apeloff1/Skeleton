import pytest

from skeleton.frontier.gameforge_lease import LeaseSet


def test_lease_set_is_bounded_and_releases():
    leases = LeaseSet(1)
    first = leases.acquire("a")
    assert first is not None
    assert leases.remaining == 0
    assert leases.acquire("b") is None
    first.release()
    assert leases.active == 0
    assert leases.remaining == 1
    second = leases.acquire("b")
    assert second is not None


def test_lease_cannot_release_twice():
    lease = LeaseSet().acquire("a")
    assert lease is not None
    lease.release()
    with pytest.raises(RuntimeError):
        lease.release()


def test_lease_rejects_invalid_tokens():
    leases = LeaseSet()
    with pytest.raises(ValueError):
        leases.acquire("")
    with pytest.raises(ValueError):
        leases.acquire("   ")
    with pytest.raises(ValueError):
        leases.acquire(None)  # type: ignore[arg-type]


def test_lease_capacity_rejects_boolean():
    with pytest.raises(ValueError):
        LeaseSet(True)
