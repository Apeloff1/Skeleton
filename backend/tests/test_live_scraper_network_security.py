from __future__ import annotations

import asyncio
import socket

import httpx
import pytest

from services import live_scrapers as scrapers


class _OversizedStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield b"x" * scrapers.SIZE_CAP
        yield b"y"


def _run_get(
    url: str,
    handler,
    monkeypatch: pytest.MonkeyPatch,
    *,
    resolver=None,
) -> str | None:
    monkeypatch.setattr(scrapers, "HOST_DELAY", 0.0)
    scrapers.HOST_GUARD.clear()

    if resolver is None:
        async def resolver(_host: str, _port: int) -> tuple[str, ...]:
            return ("8.8.8.8",)
    monkeypatch.setattr(scrapers, "_resolve_public_host", resolver)

    async def run() -> str | None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(
            transport=transport,
            follow_redirects=False,
            timeout=scrapers.TIMEOUT,
        ) as client:
            return await scrapers._polite_get(client, url)

    return asyncio.run(run())


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/feed",
        "https://localhost/feed",
        "https://service.localhost/feed",
        "https://127.0.0.1/feed",
        "https://10.0.0.1/feed",
        "https://169.254.169.254/latest/meta-data",
        "https://2130706433/feed",
        "https://[::1]/feed",
        "https://metadata.google.internal/computeMetadata/v1/",
        "https://user:password@example.com/feed",
    ],
)
def test_scrape_url_policy_rejects_local_private_or_ambiguous_targets(url: str) -> None:
    with pytest.raises(ValueError):
        scrapers._validated_scrape_url(url)


def test_scrape_url_policy_allows_public_https_and_query() -> None:
    url, host = scrapers._validated_scrape_url("https://github.com/trending?since=daily")
    assert url == "https://github.com/trending?since=daily"
    assert host == "github.com"


def test_redirect_to_metadata_target_is_rejected_before_second_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(
            302,
            headers={"Location": "http://169.254.169.254/latest/meta-data"},
        )

    assert _run_get("https://public.example/feed", handler, monkeypatch) is None
    assert seen == ["https://public.example/feed"]


def test_redirect_to_private_https_literal_is_rejected_before_second_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://10.0.0.9/internal"})

    assert _run_get("https://public.example/feed", handler, monkeypatch) is None
    assert len(seen) == 1


def test_safe_https_redirect_is_followed_manually(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.host == "public.example":
            return httpx.Response(302, headers={"Location": "https://cdn.example/feed"})
        return httpx.Response(200, content=b"ok")

    assert _run_get("https://public.example/feed", handler, monkeypatch) == "ok"
    assert seen == ["https://public.example/feed", "https://cdn.example/feed"]


def test_declared_oversized_response_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Length": str(scrapers.SIZE_CAP + 1)},
            content=b"x",
        )

    assert _run_get("https://public.example/feed", handler, monkeypatch) is None


def test_streamed_oversized_response_is_rejected_without_content_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=_OversizedStream())

    assert _run_get("https://public.example/feed", handler, monkeypatch) is None


def test_bounded_response_is_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<rss>safe</rss>")

    assert _run_get("https://public.example/feed", handler, monkeypatch) == "<rss>safe</rss>"



def _dns_row(address: str):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    sockaddr = (address, 443, 0, 0) if family == socket.AF_INET6 else (address, 443)
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)


def test_dns_resolution_rejects_private_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        scrapers.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [_dns_row("127.0.0.1")],
    )

    with pytest.raises(ValueError, match="non-public"):
        asyncio.run(scrapers._resolve_public_host("public.example", 443))


def test_dns_resolution_rejects_mixed_public_and_private_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        scrapers.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            _dns_row("8.8.8.8"),
            _dns_row("10.0.0.7"),
        ],
    )

    with pytest.raises(ValueError, match="non-public"):
        asyncio.run(scrapers._resolve_public_host("mixed.example", 443))


def test_dns_resolution_accepts_only_public_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        scrapers.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            _dns_row("8.8.8.8"),
            _dns_row("1.1.1.1"),
            _dns_row("8.8.8.8"),
        ],
    )

    resolved = asyncio.run(scrapers._resolve_public_host("public.example", 443))

    assert resolved == ("1.1.1.1", "8.8.8.8")


def test_dns_resolution_failure_is_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args, **_kwargs):
        raise socket.gaierror("SECRET_DNS_DETAIL")

    monkeypatch.setattr(scrapers.socket, "getaddrinfo", fail)

    with pytest.raises(ValueError, match="resolution failed") as excinfo:
        asyncio.run(scrapers._resolve_public_host("public.example", 443))

    assert "SECRET_DNS_DETAIL" not in str(excinfo.value)


def test_private_dns_resolution_is_rejected_before_http_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    async def reject_private(_host: str, _port: int) -> tuple[str, ...]:
        raise ValueError("non-public")

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=b"should-not-run")

    assert (
        _run_get(
            "https://public.example/feed",
            handler,
            monkeypatch,
            resolver=reject_private,
        )
        is None
    )
    assert seen == []


def test_redirect_dns_policy_is_rechecked_before_second_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    async def resolve(host: str, _port: int) -> tuple[str, ...]:
        if host == "internal.example":
            raise ValueError("non-public")
        return ("8.8.8.8",)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(
            302,
            headers={"Location": "https://internal.example/private"},
        )

    assert (
        _run_get(
            "https://public.example/feed",
            handler,
            monkeypatch,
            resolver=resolve,
        )
        is None
    )
    assert seen == ["https://public.example/feed"]
