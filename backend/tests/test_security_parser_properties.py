"""Bounded deterministic property tests for network-edge security parsers."""

from __future__ import annotations

import asyncio
import ipaddress
import random
import string

import pytest
from starlette.requests import Request
from starlette.responses import Response

import api_middleware
from middleware.security import SizeLimitMiddleware, _matches_api_boundary


SEED = 0x5EC0_2026
SAMPLES = 96


def _request(
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
    peer: str = "192.0.2.10",
    path: str = "/api/test",
) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("ascii", errors="ignore"),
            "query_string": b"",
            "headers": headers or [],
            "client": (peer, 12345),
            "server": ("test", 80),
        }
    )


def _assert_uuid4_hex(value: str) -> None:
    assert len(value) == 32
    assert value.isascii()
    int(value, 16)


def test_request_id_allowed_charset_round_trips_property() -> None:
    rng = random.Random(SEED)
    alphabet = string.ascii_letters + string.digits + "._:-"

    for _ in range(SAMPLES):
        length = rng.randint(1, 128)
        candidate = "".join(rng.choice(alphabet) for _ in range(length))
        request = _request(headers=[(b"x-request-id", candidate.encode("ascii"))])
        assert api_middleware._request_id(request) == candidate


def test_request_id_malformed_inputs_are_replaced_property() -> None:
    rng = random.Random(SEED + 1)
    forbidden = " \t\r\n/\\,;=\x00"

    for _ in range(SAMPLES):
        length = rng.randint(1, 80)
        chars = [rng.choice(string.ascii_letters + string.digits) for _ in range(length)]
        chars[rng.randrange(length)] = rng.choice(forbidden)
        candidate = "".join(chars)
        request = _request(headers=[(b"x-request-id", candidate.encode("latin-1"))])
        generated = api_middleware._request_id(request)
        _assert_uuid4_hex(generated)
        assert generated != candidate

    oversized = "a" * 129
    generated = api_middleware._request_id(
        _request(headers=[(b"x-request-id", oversized.encode("ascii"))])
    )
    _assert_uuid4_hex(generated)


def test_request_id_duplicate_fields_fail_closed_property() -> None:
    rng = random.Random(SEED + 2)

    for _ in range(SAMPLES):
        token = f"trace-{rng.getrandbits(64):016x}"
        request = _request(
            headers=[
                (b"x-request-id", token.encode("ascii")),
                (b"x-request-id", token.encode("ascii")),
            ]
        )
        generated = api_middleware._request_id(request)
        _assert_uuid4_hex(generated)
        assert generated != token


def test_untrusted_peer_ignores_forwarded_identity_property(monkeypatch) -> None:
    rng = random.Random(SEED + 3)
    monkeypatch.setattr(
        api_middleware,
        "_TRUSTED_PROXY_NETWORKS",
        (ipaddress.ip_network("10.0.0.0/8"),),
    )

    for _ in range(SAMPLES):
        claimed = f"203.0.113.{rng.randint(1, 254)}"
        request = _request(
            peer="198.51.100.77",
            headers=[(b"x-forwarded-for", claimed.encode("ascii"))],
        )
        assert api_middleware._client_ip(request) == "198.51.100.77"


def test_trusted_proxy_selects_nearest_untrusted_hop_property(monkeypatch) -> None:
    rng = random.Random(SEED + 4)
    monkeypatch.setattr(
        api_middleware,
        "_TRUSTED_PROXY_NETWORKS",
        (ipaddress.ip_network("10.0.0.0/8"),),
    )

    for _ in range(SAMPLES):
        client = f"203.0.113.{rng.randint(1, 254)}"
        trusted_hop = f"10.{rng.randint(1, 254)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"
        chain = f"{client}, {trusted_hop}"
        request = _request(
            peer="10.0.0.2",
            headers=[(b"x-forwarded-for", chain.encode("ascii"))],
        )
        assert api_middleware._client_ip(request) == client


def test_malformed_or_duplicate_xff_fails_closed_property(monkeypatch) -> None:
    rng = random.Random(SEED + 5)
    monkeypatch.setattr(
        api_middleware,
        "_TRUSTED_PROXY_NETWORKS",
        (ipaddress.ip_network("10.0.0.0/8"),),
    )

    malformed = ["", ",", "203.0.113.1,,10.0.0.3", "not-an-ip", "203.0.113.1, nope"]
    malformed.extend(
        "".join(rng.choice(string.ascii_letters + ".:-,") for _ in range(rng.randint(1, 40)))
        for _ in range(SAMPLES)
    )

    for value in malformed:
        request = _request(
            peer="10.0.0.2",
            headers=[(b"x-forwarded-for", value.encode("ascii"))],
        )
        assert api_middleware._client_ip(request) == "10.0.0.2"

    duplicated = _request(
        peer="10.0.0.2",
        headers=[
            (b"x-forwarded-for", b"203.0.113.1"),
            (b"x-forwarded-for", b"203.0.113.2"),
        ],
    )
    assert api_middleware._client_ip(duplicated) == "10.0.0.2"


def test_api_path_boundary_property() -> None:
    rng = random.Random(SEED + 6)
    alphabet = string.ascii_letters + string.digits + "_-"

    assert api_middleware._matches_path_prefix("/api")
    assert _matches_api_boundary("/api")

    for _ in range(SAMPLES):
        segment = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 32)))
        child = f"/api/{segment}"
        lookalike = f"/api{segment}"
        assert api_middleware._matches_path_prefix(child)
        assert _matches_api_boundary(child)
        assert not api_middleware._matches_path_prefix(lookalike)
        assert not _matches_api_boundary(lookalike)


def test_positive_integer_config_parser_property(monkeypatch) -> None:
    rng = random.Random(SEED + 7)
    name = "SKELETON_TEST_POSITIVE_INT"

    for _ in range(SAMPLES):
        expected = rng.randint(1, 10_000_000)
        monkeypatch.setenv(name, str(expected))
        assert api_middleware._positive_int_env(name, 1) == expected

    for invalid in ("0", "-1", "-999", "1.5", "nan", "inf", "", "text"):
        monkeypatch.setenv(name, invalid)
        with pytest.raises(RuntimeError):
            api_middleware._positive_int_env(name, 1)


def test_positive_float_config_parser_property(monkeypatch) -> None:
    rng = random.Random(SEED + 8)
    name = "SKELETON_TEST_POSITIVE_FLOAT"

    for _ in range(SAMPLES):
        expected = rng.uniform(0.001, 100_000.0)
        monkeypatch.setenv(name, repr(expected))
        assert api_middleware._positive_float_env(name, 1.0) == expected

    for invalid in ("0", "-1", "nan", "inf", "-inf", "", "text"):
        monkeypatch.setenv(name, invalid)
        with pytest.raises(RuntimeError):
            api_middleware._positive_float_env(name, 1.0)


async def _exercise_size_limit(
    *,
    content_length: bytes | None,
    chunks: list[bytes],
) -> tuple[int, bool, bytes]:
    queue = [
        {
            "type": "http.request",
            "body": chunk,
            "more_body": index < len(chunks) - 1,
        }
        for index, chunk in enumerate(chunks)
    ] or [{"type": "http.request", "body": b"", "more_body": False}]
    sent: list[dict] = []
    called = False
    observed = bytearray()

    async def receive() -> dict:
        return queue.pop(0)

    async def send(message: dict) -> None:
        sent.append(message)

    async def app(scope, bounded_receive, bounded_send) -> None:
        nonlocal called
        called = True
        while True:
            message = await bounded_receive()
            observed.extend(message.get("body") or b"")
            if not message.get("more_body", False):
                break
        response = Response(status_code=204)
        await response(scope, bounded_receive, bounded_send)

    headers = [] if content_length is None else [(b"content-length", content_length)]
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/property",
        "raw_path": b"/api/property",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }

    await SizeLimitMiddleware(app, max_mb=1)(scope, receive, send)
    status = next(
        message["status"]
        for message in sent
        if message["type"] == "http.response.start"
    )
    return status, called, bytes(observed)


def test_content_length_malformed_values_reject_without_parser_crash_property() -> None:
    rng = random.Random(SEED + 9)
    alphabet = string.ascii_letters + "+-.,x_;:/"

    for _ in range(SAMPLES):
        value = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 64)))
        status, called, _ = asyncio.run(
            _exercise_size_limit(content_length=value.encode("ascii"), chunks=[b"x"])
        )
        assert status == 400
        assert not called

    huge_declared = b"9" * 4096
    status, called, _ = asyncio.run(
        _exercise_size_limit(content_length=huge_declared, chunks=[b""])
    )
    assert status == 413
    assert not called


def test_content_length_exact_match_and_mismatch_property() -> None:
    rng = random.Random(SEED + 10)

    for _ in range(SAMPLES):
        size = rng.randint(0, 2048)
        body = bytes(rng.getrandbits(8) for _ in range(size))
        status, called, observed = asyncio.run(
            _exercise_size_limit(
                content_length=str(size).encode("ascii"),
                chunks=[body],
            )
        )
        assert status == 204
        assert called
        assert observed == body

        mismatch = size + 1
        status, called, _ = asyncio.run(
            _exercise_size_limit(
                content_length=str(mismatch).encode("ascii"),
                chunks=[body],
            )
        )
        assert status == 400
        assert not called


def test_streamed_body_replay_preserves_bytes_property() -> None:
    rng = random.Random(SEED + 11)

    for _ in range(32):
        chunks = [
            bytes(rng.getrandbits(8) for _ in range(rng.randint(0, 512)))
            for _ in range(rng.randint(1, 8))
        ]
        expected = b"".join(chunks)
        status, called, observed = asyncio.run(
            _exercise_size_limit(content_length=None, chunks=chunks)
        )
        assert status == 204
        assert called
        assert observed == expected
