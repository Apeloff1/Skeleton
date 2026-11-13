import pytest

from core.core_v1.clock import FakeClock
from core.core_v1.errors import CoreError
from core.core_v1.idempotency import Idempotency, StoredResponse, fingerprint
from core.core_v1.memory_store import MemoryIdempotencyStore
from core.core_v1.models import SubscriptionDraft, filter_matches, validate_draft, validate_event_type


@pytest.mark.parametrize("pat,evt,ok", [
    ("project.*", "project.created", True), ("project.*", "project.build.done", False),
    ("project.created", "project.created", True), ("project.*", "build.done", False)])
def test_filter_matching(pat, evt, ok):
    assert filter_matches(pat, evt) is ok


def test_draft_validation():
    d = validate_draft(SubscriptionDraft("https://x", ("b.c", "a.*", "b.c")))
    assert d.event_filters == ("a.*", "b.c")
    for bad in (SubscriptionDraft("u", ("Bad",)), SubscriptionDraft("u", max_attempts=0),
                SubscriptionDraft("u", description="x" * 281), SubscriptionDraft("u", extra={"secret": 1})):
        with pytest.raises(CoreError):
            validate_draft(bad)
    with pytest.raises(CoreError):
        validate_event_type("noperiod")
    with pytest.raises(CoreError):  # leading wildcard is not a valid filter
        validate_draft(SubscriptionDraft("u", ("*.created",)))


def _idem():
    clock = FakeClock()
    return Idempotency(MemoryIdempotencyStore(), clock), clock


def test_replay_same_request():
    idem, _ = _idem()
    calls = []
    act = lambda: calls.append(1) or StoredResponse(201, {"n": len(calls)})
    fp = fingerprint("POST", "r", {"a": 1})
    r1, rep1 = idem.run("key-00001", ("t", "a", "r"), fp, act)
    r2, rep2 = idem.run("key-00001", ("t", "a", "r"), fp, act)
    assert (rep1, rep2) == (False, True) and r1 == r2 and len(calls) == 1


def test_key_reuse_and_scope():
    idem, _ = _idem()
    act = lambda: StoredResponse(201, {})
    idem.run("key-00001", ("t", "a", "r"), "fp1", act)
    with pytest.raises(CoreError) as ei:
        idem.run("key-00001", ("t", "a", "r"), "fp2", act)
    assert ei.value.code == "CORE.IDEMPOTENCY.KEY_REUSED"
    _, replayed = idem.run("key-00001", ("t", "OTHER", "r"), "fp2", act)
    assert replayed is False


def test_errors_release_key_and_expiry():
    idem, clock = _idem()

    def boom():
        raise RuntimeError("x")
    with pytest.raises(RuntimeError):
        idem.run("key-00001", ("t", "a", "r"), "fp", boom)
    _, rep = idem.run("key-00001", ("t", "a", "r"), "fp", lambda: StoredResponse(500, {}))
    assert rep is False
    r, rep = idem.run("key-00001", ("t", "a", "r"), "fp", lambda: StoredResponse(201, {"ok": 1}))
    assert rep is False
    clock.advance(24 * 3600 + 1)
    r2, rep = idem.run("key-00001", ("t", "a", "r"), "fp-new", lambda: StoredResponse(201, {"ok": 2}))
    assert rep is False and r2.body == {"ok": 2}


def test_bad_key_and_no_key():
    idem, _ = _idem()
    with pytest.raises(CoreError):
        idem.run("short", ("t", "a", "r"), "fp", lambda: StoredResponse(200, {}))
    assert idem.run(None, ("t", "a", "r"), "fp", lambda: StoredResponse(200, {}))[1] is False


def test_idempotency_scope_serialization_prevents_delimiter_collisions():
    from core.core_v1.idempotency import scope_key

    assert scope_key("tenant|actor", "user", "route", "key-00001") != scope_key(
        "tenant", "actor|user", "route", "key-00001"
    )
    idem, _ = _idem()
    first = lambda: StoredResponse(201, {"tenant": 1})
    second = lambda: StoredResponse(201, {"tenant": 2})
    idem.run("key-00001", ("tenant|actor", "user", "route"), "same", first)
    response, replayed = idem.run("key-00001", ("tenant", "actor|user", "route"), "same", second)
    assert not replayed and response.body == {"tenant": 2}
    with pytest.raises(CoreError):
        idem.run(123, ("t", "a", "r"), "fp", first)
