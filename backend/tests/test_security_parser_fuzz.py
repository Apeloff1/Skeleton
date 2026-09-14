"""Deterministic bounded fuzz/property tests for security boundary parsers."""
from __future__ import annotations

import random
import string

import pytest
from starlette.requests import Request

from api_middleware import _request_id, _safe_log_field
from core import security_config
from core.client_ip import resolve_client_ip
from middleware.security import _safe_content_length, _safe_text

SEED = 0x5EC0_2026


def _random_text(rng: random.Random, *, max_length: int = 96) -> str:
    alphabet = string.ascii_letters + string.digits + string.punctuation + " \t\r\n\x00\x7f"
    return "".join(rng.choice(alphabet) for _ in range(rng.randint(0, max_length)))


def _request(peer: str, headers: list[tuple[bytes, bytes]]) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/api/fuzz",
            "raw_path": b"/api/fuzz",
            "query_string": b"",
            "headers": headers,
            "client": (peer, 43210),
            "server": ("testserver", 443),
        }
    )


def test_malformed_forwarded_headers_fail_closed_without_crashing(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    security_config.clear_security_config_caches()
    rng = random.Random(SEED)

    for _ in range(2_000):
        token = "bad-" + _random_text(rng, max_length=128)
        request = _request(
            "10.0.0.2",
            [(b"x-forwarded-for", token.encode("latin-1", errors="replace"))],
        )
        assert resolve_client_ip(request) == "10.0.0.2"


def test_untrusted_peer_identity_is_invariant_under_random_forwarded_headers(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "10.0.0.0/8,127.0.0.0/8,::1/128")
    security_config.clear_security_config_caches()
    rng = random.Random(SEED + 1)
    peer = "198.51.100.77"

    for _ in range(2_000):
        xff = _random_text(rng, max_length=128)
        request = _request(peer, [(b"x-forwarded-for", xff.encode("latin-1", errors="replace"))])
        assert resolve_client_ip(request) == peer


def test_content_length_parser_is_total_for_adversarial_text() -> None:
    rng = random.Random(SEED + 2)

    for _ in range(4_000):
        value = _random_text(rng, max_length=64)
        result = _safe_content_length(value)
        assert result is None or isinstance(result, int)
        if result is not None:
            assert result == -1 or result >= 0


def test_request_id_parser_never_reflects_control_characters() -> None:
    rng = random.Random(SEED + 3)

    for _ in range(2_000):
        value = _random_text(rng, max_length=300)
        request = _request(
            "198.51.100.10",
            [(b"x-request-id", value.encode("latin-1", errors="replace"))],
        )
        request_id = _request_id(request)
        assert 1 <= len(request_id) <= 128
        assert "\r" not in request_id
        assert "\n" not in request_id
        assert "\t" not in request_id
        assert "\x00" not in request_id
        assert "\x7f" not in request_id
        assert all(ch.isalnum() or ch in "._:-" for ch in request_id)


def test_log_sanitizers_are_bounded_and_single_line_under_random_input() -> None:
    rng = random.Random(SEED + 4)

    for _ in range(4_000):
        value = _random_text(rng, max_length=2048)
        limit = rng.randint(1, 256)
        for safe in (_safe_text(value, limit), _safe_log_field(value, limit)):
            assert len(safe) <= limit
            assert "\r" not in safe
            assert "\n" not in safe
            assert "\x00" not in safe
            assert "\x7f" not in safe


def test_security_integer_config_fails_closed_for_random_invalid_production_values(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    rng = random.Random(SEED + 5)
    alphabet = string.ascii_letters + "!@#$%^&*"

    for _ in range(500):
        value = "x" + "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 24)))
        monkeypatch.setenv("FUZZ_SECURITY_INT", value)
        with pytest.raises(security_config.SecurityConfigError):
            security_config.env_int("FUZZ_SECURITY_INT", 10, minimum=1, maximum=100)


def test_security_integer_config_preserves_bounds_for_random_development_values(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    rng = random.Random(SEED + 6)

    for _ in range(2_000):
        monkeypatch.setenv("FUZZ_SECURITY_INT", _random_text(rng, max_length=32))
        value = security_config.env_int("FUZZ_SECURITY_INT", 25, minimum=1, maximum=100)
        assert 1 <= value <= 100


def test_production_random_invalid_booleans_fail_closed(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    rng = random.Random(SEED + 7)
    accepted = {"1", "0", "true", "false", "yes", "no", "on", "off"}
    checked = 0

    for _ in range(1_000):
        raw = _random_text(rng, max_length=24)
        if raw.strip().lower() in accepted:
            continue
        monkeypatch.setenv("FUZZ_SECURITY_BOOL", raw)
        with pytest.raises(security_config.SecurityConfigError):
            security_config.env_bool("FUZZ_SECURITY_BOOL", True)
        checked += 1

    assert checked > 900
