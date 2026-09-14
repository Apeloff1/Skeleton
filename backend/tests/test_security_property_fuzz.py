"""Deterministic bounded fuzz/property coverage for security-boundary parsers."""
from __future__ import annotations

import random
import string

from starlette.requests import Request

import api_middleware
from core import security_config
from core.client_ip import _trusted_networks, resolve_client_ip
from middleware.security import _safe_content_length, _safe_text


SEED = 0x5EC0_2026


def _random_text(rng: random.Random, *, max_length: int = 96) -> str:
    alphabet = string.ascii_letters + string.digits + string.punctuation + " \t\r\n\x00\x7f"
    return "".join(rng.choice(alphabet) for _ in range(rng.randint(0, max_length)))


def _request(peer: str, xff: str | None = None, request_id: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode("latin-1", errors="replace")))
    if request_id is not None:
        headers.append((b"x-request-id", request_id.encode("latin-1", errors="replace")))
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": "/api/fuzz",
            "raw_path": b"/api/fuzz",
            "query_string": b"",
            "headers": headers,
            "client": (peer, 44321),
            "server": ("testserver", 443),
        }
    )


def test_content_length_parser_never_raises_on_bounded_text_corpus() -> None:
    rng = random.Random(SEED)
    for _ in range(4_000):
        value = _random_text(rng, max_length=64)
        parsed = _safe_content_length(value)
        assert parsed is None or parsed == -1 or parsed >= 0


def test_log_sanitizers_are_single_line_and_bounded_for_adversarial_text() -> None:
    rng = random.Random(SEED + 1)
    for _ in range(4_000):
        value = _random_text(rng, max_length=1024)
        limit = rng.randint(1, 256)
        for sanitized in (
            api_middleware._safe_log_field(value, limit),
            _safe_text(value, limit),
        ):
            assert len(sanitized) <= limit
            assert "\r" not in sanitized
            assert "\n" not in sanitized
            assert "\x00" not in sanitized
            assert "\x7f" not in sanitized


def test_request_id_normalization_never_reflects_control_characters() -> None:
    rng = random.Random(SEED + 2)
    for _ in range(2_000):
        supplied = _random_text(rng, max_length=256)
        normalized = api_middleware._request_id(_request("198.51.100.7", request_id=supplied))
        assert 1 <= len(normalized) <= 128
        assert all(ch.isalnum() or ch in "._:-" for ch in normalized)
        assert "\r" not in normalized and "\n" not in normalized


def test_untrusted_peer_identity_is_invariant_under_random_forwarded_headers(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "10.0.0.0/8,127.0.0.0/8,::1/128")
    security_config.clear_security_config_caches()
    _trusted_networks.cache_clear()

    rng = random.Random(SEED + 3)
    peer = "198.51.100.77"
    for _ in range(2_000):
        xff = _random_text(rng, max_length=128)
        assert resolve_client_ip(_request(peer, xff=xff)) == peer


def test_security_integer_parser_preserves_bounds_for_random_inputs(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "development")
    rng = random.Random(SEED + 4)
    for _ in range(2_000):
        raw = _random_text(rng, max_length=32)
        monkeypatch.setenv("FUZZ_SECURITY_LIMIT", raw)
        value = security_config.env_int("FUZZ_SECURITY_LIMIT", 25, minimum=1, maximum=100)
        assert 1 <= value <= 100


def test_production_random_invalid_booleans_fail_closed(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    rng = random.Random(SEED + 5)
    accepted = {"1", "0", "true", "false", "yes", "no", "on", "off"}
    checked = 0
    for _ in range(1_000):
        raw = _random_text(rng, max_length=24)
        if raw.strip().lower() in accepted:
            continue
        monkeypatch.setenv("FUZZ_SECURITY_BOOL", raw)
        try:
            security_config.env_bool("FUZZ_SECURITY_BOOL", True)
        except security_config.SecurityConfigError:
            checked += 1
        else:
            raise AssertionError(f"ambiguous production boolean was accepted: {raw!r}")
    assert checked > 900
