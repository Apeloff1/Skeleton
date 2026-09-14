from __future__ import annotations

import random
import string

import pytest
from starlette.requests import Request

from api_middleware import _request_id
from core import security_config
from core.client_ip import resolve_client_ip
from middleware.security import _safe_content_length, _safe_text


def _request(peer: str, headers: list[tuple[bytes, bytes]]) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/fuzz",
            "raw_path": b"/api/fuzz",
            "query_string": b"",
            "headers": headers,
            "client": (peer, 43210),
            "server": ("testserver", 80),
        }
    )


def test_malformed_forwarded_headers_fail_closed_without_crashing(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    security_config.clear_security_config_caches()
    rng = random.Random(20260914)
    alphabet = string.ascii_letters + " !@#$%^&*()[]{};|/\\"

    for _ in range(500):
        token = "bad-" + "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 64)))
        request = _request("10.0.0.2", [(b"x-forwarded-for", token.encode("latin-1", "ignore"))])
        assert resolve_client_ip(request) == "10.0.0.2"


def test_content_length_parser_is_total_for_adversarial_text() -> None:
    rng = random.Random(7)
    alphabet = string.printable

    for _ in range(1000):
        value = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40)))
        result = _safe_content_length(value)
        assert result is None or isinstance(result, int)
        if result is not None:
            assert result == -1 or result >= 0


def test_request_id_parser_never_reflects_control_characters() -> None:
    rng = random.Random(42)
    alphabet = "abcXYZ0123-_.:" + "\r\n\t\x00\x1f\x7f"

    for _ in range(400):
        value = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 300)))
        request = _request("198.51.100.10", [(b"x-request-id", value.encode("latin-1"))])
        request_id = _request_id(request)
        assert "\r" not in request_id
        assert "\n" not in request_id
        assert "\t" not in request_id
        assert "\x00" not in request_id
        assert 1 <= len(request_id) <= 128


def test_safe_text_is_bounded_and_single_line_under_random_input() -> None:
    rng = random.Random(99)
    alphabet = string.printable + "\x00\x1f\x7f"

    for _ in range(500):
        value = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 2048)))
        safe = _safe_text(value, 128)
        assert len(safe) <= 128
        assert "\r" not in safe
        assert "\n" not in safe
        assert "\x00" not in safe


def test_security_integer_config_fails_closed_for_random_invalid_production_values(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    rng = random.Random(123)
    alphabet = string.ascii_letters + "!@#$%^&*"

    for _ in range(100):
        value = "x" + "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 24)))
        monkeypatch.setenv("FUZZ_SECURITY_INT", value)
        with pytest.raises(security_config.SecurityConfigError):
            security_config.env_int("FUZZ_SECURITY_INT", 10, minimum=1, maximum=100)
