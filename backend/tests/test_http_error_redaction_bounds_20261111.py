"""Source-bounded privacy regression tests for shared route error handling."""
from __future__ import annotations

import json
import math

import pytest

from core.http_errors import REDACTED, redact_client_payload, redact_client_text


@pytest.mark.parametrize(
    "raw",
    [
        "authorization=Bearer dangerous-secret",
        "Bearer dangerous-secret",
        "token=dangerous-secret",
        "password: dangerous-secret",
        "https://example.test/path?token=dangerous-secret&offset=1",
        "https://example.test/path?api_key=dangerous-secret",
        '{"token":"dangerous-secret","safe":true}',
        '{"authorization": "dangerous-secret"}',
        '{"refresh_token" : "dangerous-secret"}',
    ],
)
def test_redacted_error_text_never_contains_secret(raw):
    assert "dangerous-secret" not in redact_client_text(raw)


def test_large_error_text_is_clamped_before_regex_and_output():
    raw = "a" * 2_000_000
    output = redact_client_text(raw)
    assert len(output) == 2000
    assert output == "a" * 2000
    with pytest.raises(ValueError):
        redact_client_text(raw, max_len=16_385)
    with pytest.raises(ValueError):
        redact_client_text(raw, max_len=-1)
    with pytest.raises(ValueError):
        redact_client_text(raw, max_len=True)


def test_secrets_embedded_near_output_budget_boundary_are_not_exposed():
    raw = "a" * 1985 + " token=dangerous-secret&next=ok"
    assert "dangerous-secret" not in redact_client_text(raw)
    raw = "a" * 1980 + " Bearer dangerous-secret-value"
    assert "dangerous-secret" not in redact_client_text(raw)


def test_huge_dict_is_iterated_only_to_output_budget():
    class UnlimitedKeys(dict):
        def items(self):
            for i in range(1_000_000):
                if i > 50:
                    raise AssertionError("redactor traversed beyond bounded key budget")
                yield f"field_{i}", f"value_{i}"

    sanitized = redact_client_payload(UnlimitedKeys())
    assert len(sanitized) == 50
    assert sanitized["field_0"] == "value_0"


def test_nested_secret_keys_and_proto_pollution_keys_are_never_exposed():
    payload = {
        "client-secret": "dangerous-secret",
        "nested": {"session_token": "dangerous-secret", "visible": "yes"},
        "__proto__": {"poisoned": True},
        "constructor": {"prototype": "attack"},
        "items": [{"Authorization": "dangerous-secret"}],
    }
    sanitized = redact_client_payload(payload)
    assert sanitized["client-secret"] == REDACTED
    assert sanitized["nested"]["session_token"] == REDACTED
    assert sanitized["nested"]["visible"] == "yes"
    assert "__proto__" not in sanitized and "constructor" not in sanitized
    assert "dangerous-secret" not in json.dumps(sanitized)


def test_arbitrary_object_stringification_is_not_executed():
    class LeakingObject:
        def __str__(self):
            raise AssertionError("object conversion must not run")

        def __repr__(self):
            raise AssertionError("object repr must not run")

    sanitized = redact_client_payload({
        "private": LeakingObject(),
        "safe": [LeakingObject()],
        42: LeakingObject(),
    })
    assert sanitized["private"] == "[UNSUPPORTED]"
    assert sanitized["safe"] == ["[UNSUPPORTED]"]
    assert 42 not in sanitized


def test_circular_payload_bounded_and_nonfinite_numbers_not_json_emitted():
    payload: dict = {"safe": 1}
    payload["self"] = payload
    payload["numeric"] = [math.nan, math.inf, -math.inf]
    sanitized = redact_client_payload(payload)
    assert sanitized["self"]["self"]["self"]["self"] == "[TRUNCATED]"
    assert sanitized["numeric"] == [None, None, None]
    assert json.loads(json.dumps(sanitized))["safe"] == 1


def test_url_secret_redaction_preserves_nonsecret_query_attributes():
    result = redact_client_text(
        "https://example.test/search?token=dangerous-secret&query=galaxy"
    )
    assert "?token=[REDACTED]&query=galaxy" in result
