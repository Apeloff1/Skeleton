from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from starlette.responses import Response

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from middleware.security import AuditMiddleware, SizeLimitMiddleware  # noqa: E402


def _exercise(
    headers: list[tuple[bytes, bytes]],
    *,
    path: str = "/api/run",
) -> tuple[int, dict | None]:
    sent: list[dict] = []
    queue = [{"type": "http.request", "body": b"", "more_body": False}]

    async def receive() -> dict:
        return queue.pop(0)

    async def send(message: dict) -> None:
        sent.append(message)

    async def app(scope, receive, send) -> None:
        response = Response(status_code=204)
        await response(scope, receive, send)

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }

    AuditMiddleware._buf.clear()
    stack = AuditMiddleware(SizeLimitMiddleware(app, max_mb=1))
    asyncio.run(stack(scope, receive, send))

    status = next(
        message["status"]
        for message in sent
        if message["type"] == "http.response.start"
    )
    rows = AuditMiddleware.snapshot(limit=1)["entries"]
    return status, rows[-1] if rows else None


def test_malformed_content_length_is_rejected_without_audit_crash() -> None:
    status, audit = _exercise([(b"content-length", b"+1")])

    assert status == 400
    assert audit is not None
    assert audit["status"] == 400
    assert audit["req_bytes"] == 0


def test_absurd_content_length_is_rejected_without_integer_conversion() -> None:
    status, audit = _exercise([(b"content-length", b"9" * 10_000)])

    assert status == 413
    assert audit is not None
    assert audit["status"] == 413
    assert audit["req_bytes"] == 0


def test_audit_uses_direct_peer_not_spoofed_forwarding_header() -> None:
    status, audit = _exercise(
        [
            (b"content-length", b"0"),
            (b"x-forwarded-for", b"203.0.113.77"),
        ]
    )

    assert status == 204
    assert audit is not None
    assert audit["ip"] == "127.0.0.1"


def test_api_lookalike_is_not_added_to_audit_ring() -> None:
    status, audit = _exercise([(b"content-length", b"0")], path="/apiary/run")

    assert status == 204
    assert audit is None
