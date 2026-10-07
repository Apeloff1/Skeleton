import pytest

from skeleton.frontier.gameforge_lease import LeaseSet


def test_lease_release_is_idempotence_guarded():
    leases = LeaseSet(1)
    lease = leases.acquire("r1")
    assert lease is not None
    assert leases.active == 1
    lease.release()
    assert leases.active == 0
    with pytest.raises(RuntimeError):
        lease.release()
    assert leases.active == 0


def test_lease_rejects_blank_tokens():
    leases = LeaseSet()
    with pytest.raises(ValueError):
        leases.acquire(" ")
