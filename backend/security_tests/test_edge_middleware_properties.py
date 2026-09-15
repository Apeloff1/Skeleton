from __future__ import annotations

import asyncio
import random
import re
import string
import sys
from pathlib import Path

import pytest
from starlette.requests import Request
from starlette.responses import Response

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from middleware.security import (  # noqa: E402
    SizeLimitMiddleware,
    _matches_path_prefix,
    _request_client_ip,
    _safe_request_id,
)

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
_MAX_BYTES = 1024 * 1024


def _request(*, peer: str, headers: list[tuple[bytes, bytes]]) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/run",
            "raw_path": b"/api/run",
            "query_string": b"",
            "headers": headers,
            "client": (peer, 12345),
            "server": ("testserver", 80),
        }
    )


def _exercise_size_limit(raw_content_length: bytes) -> tuple[int, bool]:
    queue = [{"type": "http.request", "body": b"x", "more_body": False}]
    sent: list[dict] = []
    called = False

    async def receive() -> dict:
        return queue.pop(0)

    async def send(message: dict) -> None:
        sent.append(message)

    async def app(scope, bounded_receive, bounded_send) -> None:
        nonlocal called
        called = True
        await bounded_receive()
        response = Response(status_code=204)
        await response(scope, bounded_receive, bounded_send)

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/run",
        "raw_path": b"/api/run",
        "query_string": b"",
        "headers": [(b"content-length", raw_content_length)],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }

    asyncio.run(SizeLimitMiddleware(app, max_mb=1)(scope, receive, send))
    status = next(
        message["status"]
        for message in sent
        if message["type"] == "http.response.start"
    )
    return status, called


def _expected_content_length_status(raw: bytes) -> int:
    text = raw.decode("latin-1").strip(" \t")
    if not text.isascii() or not text.isdigit():
        return 400

    normalized = text.lstrip("0") or "0"
    limit_text = str(_MAX_BYTES)
    if len(normalized) > len(limit_text) or (
        len(normalized) == len(limit_text) and normalized > limit_text
    ):
        return 413

    return 204 if int(normalized, 10) == 1 else 400


def test_bounded_generated_content_length_corpus_is_total_and_fail_closed() -> None:
    """Exercise malformed and extreme framing without an external fuzz dependency."""
    rng = random.Random(0xC0DEC0DE)
    alphabet = b"0123456789+-_,. abcdefABCDEF\t"
    corpus = [
        b"",
        b"\xff",
        b"0" * 5000,
        b"9" * 5000,
        b"1,1",
        b"+1",
        b"-1",
        b" 1 ",
        b"000001",
    ]
    for _ in range(256):
        size = rng.randint(0, 96)
        corpus.append(bytes(rng.choice(alphabet) for _ in range(size)))

    for raw in corpus:
        status, called = _exercise_size_limit(raw)
        expected = _expected_content_length_status(raw)
        assert status == expected, raw[:120]
        assert called is (expected == 204), raw[:120]


def test_generated_forwarded_chains_resolve_or_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rng = random.Random(0xF04A4DED)
    monkeypatch.setenv("CODEDOCK_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    peer = "10.0.0.2"

    for _ in range(256):
        client = f"203.0.113.{rng.randint(1, 254)}"
        proxy = f"10.0.0.{rng.randint(3, 254)}"
        valid = f"{client}, {proxy}".encode("ascii")
        request = _request(peer=peer, headers=[(b"x-forwarded-for", valid)])
        assert _request_client_ip(request) == client

        malformed = rng.choice(
            [
                f"{client},, {proxy}",
                f"{client}, not-an-ip, {proxy}",
                f", {client}, {proxy}",
                f"{client}, {proxy},",
            ]
        ).encode("ascii")
        request = _request(peer=peer, headers=[(b"x-forwarded-for", malformed)])
        assert _request_client_ip(request) == peer

        request = _request(
            peer=peer,
            headers=[
                (b"x-forwarded-for", client.encode("ascii")),
                (b"x-forwarded-for", proxy.encode("ascii")),
            ],
        )
        assert _request_client_ip(request) == peer


def test_generated_request_ids_are_bounded_and_sanitized() -> None:
    rng = random.Random(0x1D5AFE)
    alphabet = string.ascii_letters + string.digits + "._:- /\\\n\t!@#$%^&*()"

    for _ in range(512):
        raw = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 96)))
        sanitized = _safe_request_id(raw)
        assert _REQUEST_ID_RE.fullmatch(sanitized)
        assert len(sanitized) <= 64
        if _REQUEST_ID_RE.fullmatch(raw):
            assert sanitized == raw
        else:
            assert len(sanitized) == 16
            assert all(char in string.hexdigits for char in sanitized)


def test_generated_route_lookalikes_never_cross_segment_boundary() -> None:
    rng = random.Random(0xB0A1D4A7)
    prefix = "/api/health"
    alphabet = string.ascii_letters + string.digits + "-_"

    for _ in range(512):
        suffix = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 32)))
        assert _matches_path_prefix(f"{prefix}/{suffix}", prefix)
        assert not _matches_path_prefix(f"{prefix}{suffix}", prefix)
