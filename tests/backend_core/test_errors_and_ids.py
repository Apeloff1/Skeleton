import pytest

from core.core_v1 import errors
from core.core_v1.clock import FakeClock, iso
from core.core_v1.ids import is_id, new_id


def test_envelope_shape():
    e = errors.validation("CORE.WEBHOOK.INVALID", "bad", field="url")
    assert e.envelope() == {"error": {"type": "validation_error", "code": "CORE.WEBHOOK.INVALID",
                                      "message": "bad", "context": {"field": "url"}}}
    assert e.http_status == 400


def test_code_prefix_enforced():
    with pytest.raises(ValueError):
        errors.CoreError("WEBHOOK.X", "m")


def test_registry_statuses_match_helpers():
    assert errors.CODES[errors.precondition_failed('"x"').code] == 412
    assert errors.CODES[errors.precondition_required().code] == 428
    assert errors.CODES[errors.not_found("webhook", "w").code] == 404
    assert errors.CODES[errors.unavailable().code] == 503


def test_ids():
    for kind, prefix in (("webhook", "whk_"), ("event", "evt_"), ("delivery", "dlv_"), ("secret", "whs_")):
        i = new_id(kind)
        assert i.startswith(prefix) and is_id(i, kind)
    assert not is_id("whk_zz", "webhook")
    assert not is_id(new_id("event"), "webhook")
    with pytest.raises(ValueError):
        new_id("nope")


def test_fake_clock():
    c = FakeClock(100.0)
    assert c.advance(5) == 105.0 and c.now() == 105.0
    assert iso(0).startswith("1970-01-01T00:00:00")
