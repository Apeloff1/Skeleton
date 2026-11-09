import pytest

from core.core_v1 import signing
from core.core_v1.retry import RetryPolicy, classify


def test_sign_verify_roundtrip():
    s = signing.secret_bytes(signing.new_secret())
    h = signing.sign(b'{"a":1}', [s], 1000)
    assert h.startswith("t=1000,v1=")
    assert signing.verify(h, b'{"a":1}', s, now=1100)
    assert not signing.verify(h, b'{"a":2}', s, now=1100)


def test_timestamp_tolerance():
    s = signing.secret_bytes(signing.new_secret())
    h = signing.sign(b"x", [s], 1000)
    assert not signing.verify(h, b"x", s, now=1000 + 301)
    assert signing.verify(h, b"x", s, now=1000 + 300)


def test_rotation_both_secrets_verify():
    new, old = (signing.secret_bytes(signing.new_secret()) for _ in range(2))
    h = signing.sign(b"x", [new, old], 5)
    assert h.count("v1=") == 2
    assert signing.verify(h, b"x", new, 5) and signing.verify(h, b"x", old, 5)


def test_malformed():
    assert not signing.verify("nonsense", b"x", b"k", 0)
    with pytest.raises(ValueError):
        signing.secret_bytes("short")
    with pytest.raises(ValueError):
        signing.sign(b"x", [], 0)


def test_backoff_is_deterministic_bounded_and_growing():
    p = RetryPolicy(base_seconds=10, cap_seconds=100)
    assert p.delay("d1", 1) == p.delay("d1", 1)
    assert 5 <= p.delay("d1", 1) <= 10
    assert 50 <= p.delay("d1", 8) <= 100
    with pytest.raises(ValueError):
        p.delay("d1", 0)


@pytest.mark.parametrize("code,err,want", [
    (200, "", "success"), (204, "", "success"), (429, "", "retry"), (503, "", "retry"),
    (400, "", "permanent"), (410, "", "permanent"), (None, "network:TimeoutError", "retry"),
    (None, "policy:blocked", "permanent"), (599, "", "retry")])
def test_classify(code, err, want):
    assert classify(code, err) == want
