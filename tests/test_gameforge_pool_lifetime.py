import pytest

from skeleton.frontier.gameforge_health import HealthPool


def test_repeated_checkout_does_not_reset_resource_lifetime():
    now = [0]
    pool = HealthPool(object, lambda _: True, max_age_seconds=5, clock=lambda: now[0])
    first = pool.checkout()
    now[0] = 2
    assert pool.release(first)
    assert pool.checkout() is first
    now[0] = 4
    assert pool.release(first)
    now[0] = 5
    assert pool.checkout() is not first


def test_expired_active_resource_is_not_returned_to_idle_pool():
    now = [0]
    pool = HealthPool(object, lambda _: True, max_age_seconds=1, clock=lambda: now[0])
    resource = pool.checkout()
    now[0] = 1
    assert not pool.release(resource)
    assert pool.idle == 0


def test_factory_cannot_lease_one_object_twice():
    resource = object()
    pool = HealthPool(lambda: resource, lambda _: True)
    assert pool.checkout() is resource
    with pytest.raises(RuntimeError, match="already leased"):
        pool.checkout()
    assert pool.release(resource)


@pytest.mark.parametrize("age", [float("nan"), float("inf")])
def test_lifetime_must_be_finite(age):
    with pytest.raises(ValueError):
        HealthPool(object, lambda _: True, max_age_seconds=age)
