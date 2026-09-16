import asyncio

from starlette.requests import Request
from starlette.responses import Response

from backend.api_middleware import ContentTypeValidationMiddleware


def _request(
    *,
    method: str = "POST",
    body: bytes = b"payload",
    content_type: str | None = None,
    extra_headers: list[tuple[bytes, bytes]] | None = None,
) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if body:
        headers.append((b"content-length", str(len(body)).encode("ascii")))
    else:
        headers.append((b"content-length", b"0"))
    if content_type is not None:
        headers.append((b"content-type", content_type.encode("latin-1")))
    if extra_headers:
        headers.extend(extra_headers)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": "/api/content-type-test",
        "raw_path": b"/api/content-type-test",
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }

    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


def _dispatch(request: Request) -> Response:
    middleware = ContentTypeValidationMiddleware(app=lambda *_args, **_kwargs: None)

    async def call_next(_request: Request) -> Response:
        return Response("ok", status_code=200)

    return asyncio.run(middleware.dispatch(request, call_next))


def test_accepts_json_and_structured_json_media_types():
    assert _dispatch(_request(content_type="application/json")).status_code == 200
    assert (
        _dispatch(
            _request(content_type="application/problem+json; charset=utf-8")
        ).status_code
        == 200
    )


def test_accepts_form_multipart_text_and_binary_media_types():
    allowed = (
        "application/x-www-form-urlencoded",
        "multipart/form-data; boundary=unit-test",
        "text/plain; charset=utf-8",
        "application/octet-stream",
    )
    for content_type in allowed:
        assert _dispatch(_request(content_type=content_type)).status_code == 200


def test_rejects_missing_or_unsupported_content_type_for_nonempty_body():
    assert _dispatch(_request(content_type=None)).status_code == 415
    assert _dispatch(_request(content_type="text/html")).status_code == 415


def test_rejects_duplicate_content_type_headers():
    request = _request(
        content_type="application/json",
        extra_headers=[(b"content-type", b"text/plain")],
    )
    assert _dispatch(request).status_code == 415


def test_allows_empty_request_without_content_type():
    assert _dispatch(_request(body=b"", content_type=None)).status_code == 200
