from __future__ import annotations

import asyncio
import ipaddress
import random

import pytest
from starlette.requests import Request
from starlette.responses import Response

import api_middleware
import middleware.security as legacy_security


def _request(
    *,
    path: str = "/api/run",
    peer: str = "10.0.0.7",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("ascii", "ignore"),
            "query_string": b"",
            "headers": headers or [],
            "client": (peer, 12345),
            "server": ("testserver", 80),
        }
    )


def test_generated_request_id_corpus_is_always_bounded_and_header_safe() -> None:
    rng = random.Random(0x51D5AFE)
    alphabet = list(
        b"abcXYZ019._:- /\\@\t\r\n"
    ) + [0, 1, 31, 127, 128, 255]

    for _ in range(512):
        raw = bytes(rng.choice(alphabet) for _ in range(rng.randrange(0, 260)))
        request = _request(headers=[(b"x-request-id", raw)])
        decoded = raw.decode("latin-1")

        canonical = api_middleware._request_id(request)
        legacy = legacy_security._safe_request_id(request)

        assert api_middleware._REQUEST_ID_RE.fullmatch(canonical)
        assert legacy_security._REQUEST_ID_RE.fullmatch(legacy)
        assert len(canonical) <= 128
        assert len(legacy) <= 128

        if api_middleware._REQUEST_ID_RE.fullmatch(decoded):
            assert canonical == decoded
            assert legacy == decoded
        else:
            assert len(canonical) == 32
            assert len(legacy) == 16


def test_duplicate_request_ids_never_select_an_attacker_value() -> None:
    rng = random.Random(0xD0B1CA7E)
    for _ in range(128):
        first = f"safe-{rng.randrange(1_000_000)}".encode("ascii")
        second = f"other-{rng.randrange(1_000_000)}".encode("ascii")
        request = _request(
            headers=[(b"x-request-id", first), (b"x-request-id", second)]
        )

        assert api_middleware._request_id(request) not in {
            first.decode("ascii"),
            second.decode("ascii"),
        }
        assert legacy_security._safe_request_id(request) not in {
            first.decode("ascii"),
            second.decode("ascii"),
        }


def test_generated_forwarded_chains_fail_safely_without_parser_crashes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trusted = (ipaddress.ip_network("10.0.0.0/8"),)
    monkeypatch.setattr(api_middleware, "_TRUSTED_PROXY_NETWORKS", trusted)
    rng = random.Random(0xF04A4DED)
    atoms = [
        "203.0.113.8",
        "198.51.100.11",
        "10.0.0.8",
        "2001:db8::1",
        "not-an-ip",
        "999.999.999.999",
        "",
        " ",
        "203.0.113.9\r",
        "203.0.113.9\n",
    ]

    for _ in range(256):
        chain = ",".join(rng.choice(atoms) for _ in range(rng.randrange(0, 10)))
        headers = [(b"x-forwarded-for", chain.encode("latin-1"))]
        if rng.randrange(5) == 0:
            headers.append((b"x-forwarded-for", b"203.0.113.200"))
        request = _request(headers=headers)

        primary = api_middleware._client_ip(request)
        legacy = legacy_security._client_ip(request, trusted)

        assert isinstance(primary, str) and 1 <= len(primary) <= 64
        assert isinstance(legacy, str) and 1 <= len(legacy) <= 64


def test_generated_content_lengths_are_bounded_telemetry_only() -> None:
    rng = random.Random(0xC017E17)
    alphabet = list(b"0123456789+-.xXabcdef \t") + [0, 13, 255]

    samples = [b"9" * 10_000]
    samples.extend(
        bytes(rng.choice(alphabet) for _ in range(rng.randrange(0, 300)))
        for _ in range(256)
    )

    for raw in samples:
        request = _request(headers=[(b"content-length", raw)])
        value = legacy_security.AuditMiddleware._declared_size(request)
        assert value is None or (isinstance(value, int) and 0 <= value < 10**20)


def test_generated_route_lookalikes_match_only_exact_or_child_api_paths() -> None:
    rng = random.Random(0xA91B0A7D)
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789-_ /".replace(" ", "")

    for _ in range(512):
        suffix = "".join(rng.choice(alphabet) for _ in range(rng.randrange(0, 24)))
        path = "/api" + suffix
        expected = path == "/api" or path.startswith("/api/")

        assert api_middleware._matches_path_prefix(path, "/api") is expected
        assert legacy_security._matches_route_boundary(path, "/api") is expected


def test_high_cardinality_generated_identities_keep_legacy_limiter_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        async def app(_scope, _receive, _send) -> None:
            return None

        async def call_next(_request: Request) -> Response:
            return Response(status_code=204)

        monkeypatch.setenv("CODEDOCK_TRUSTED_PROXY_CIDRS", "")
        limiter_type = legacy_security.RateLimitMiddleware
        limiter_type._buckets.clear()
        limiter_type._lock = None
        limiter_type._saturation_rejections = 0
        limiter_type._expired_pruned = 0
        middleware = limiter_type(
            app,
            rps=0.000001,
            burst=1,
            max_buckets=8,
            bucket_ttl=300,
        )

        statuses = []
        for index in range(64):
            request = _request(peer=f"198.51.100.{index + 1}")
            statuses.append((await middleware.dispatch(request, call_next)).status_code)

        assert statuses[:8] == [204] * 8
        assert statuses[8:] == [429] * 56
        assert len(limiter_type._buckets) == 8
        assert limiter_type._saturation_rejections == 56

    asyncio.run(scenario())


def test_generated_positive_integer_config_values_and_invalids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rng = random.Random(0x1A7C0F1)
    name = "SKELETON_TEST_POSITIVE_INT"

    for _ in range(96):
        expected = rng.randint(1, 10_000_000)
        monkeypatch.setenv(name, str(expected))
        assert api_middleware._positive_int_env(name, 1) == expected

    for invalid in ("0", "-1", "-999", "1.5", "nan", "inf", "", "text"):
        monkeypatch.setenv(name, invalid)
        with pytest.raises(RuntimeError):
            api_middleware._positive_int_env(name, 1)


def test_generated_positive_float_config_values_and_invalids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rng = random.Random(0xF10A7C0)
    name = "SKELETON_TEST_POSITIVE_FLOAT"

    for _ in range(96):
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

    await legacy_security.SizeLimitMiddleware(app, max_mb=1)(scope, receive, send)
    status = next(
        message["status"]
        for message in sent
        if message["type"] == "http.response.start"
    )
    return status, called, bytes(observed)


def test_content_length_exact_match_and_mismatch_property() -> None:
    rng = random.Random(0xC017E18)

    for _ in range(32):
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

        status, called, _ = asyncio.run(
            _exercise_size_limit(
                content_length=str(size + 1).encode("ascii"),
                chunks=[body],
            )
        )
        assert status == 400
        assert not called


def test_streamed_body_replay_preserves_exact_bytes_property() -> None:
    rng = random.Random(0x57AEA0D)

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
