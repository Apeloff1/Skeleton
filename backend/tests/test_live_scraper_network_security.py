from __future__ import annotations

import asyncio

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
    dns_public: bool = True,
) -> str | None:
    monkeypatch.setattr(scrapers, "HOST_DELAY", 0.0)
    scrapers.HOST_GUARD.clear()

    async def resolve(_host: str) -> bool:
        return dns_public

    monkeypatch.setattr(scrapers, "_host_resolves_public", resolve)

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



def test_dns_policy_rejects_private_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        scrapers.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (
                scrapers.socket.AF_INET,
                scrapers.socket.SOCK_STREAM,
                6,
                "",
                ("10.0.0.7", 443),
            )
        ],
    )

    assert asyncio.run(scrapers._host_resolves_public("private.example")) is False


def test_dns_policy_rejects_mixed_public_private_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        scrapers.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (
                scrapers.socket.AF_INET,
                scrapers.socket.SOCK_STREAM,
                6,
                "",
                ("93.184.216.34", 443),
            ),
            (
                scrapers.socket.AF_INET,
                scrapers.socket.SOCK_STREAM,
                6,
                "",
                ("127.0.0.1", 443),
            ),
        ],
    )

    assert asyncio.run(scrapers._host_resolves_public("mixed.example")) is False


def test_dns_policy_allows_only_global_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        scrapers.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (
                scrapers.socket.AF_INET,
                scrapers.socket.SOCK_STREAM,
                6,
                "",
                ("93.184.216.34", 443),
            )
        ],
    )

    assert asyncio.run(scrapers._host_resolves_public("public.example")) is True


def test_dns_policy_fails_closed_on_resolution_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args, **_kwargs):
        raise OSError("resolver internals must not escape")

    monkeypatch.setattr(scrapers.socket, "getaddrinfo", fail)

    assert asyncio.run(scrapers._host_resolves_public("broken.example")) is False


def test_dns_rejection_happens_before_http_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=b"should-not-run")

    assert (
        _run_get(
            "https://public.example/feed",
            handler,
            monkeypatch,
            dns_public=False,
        )
        is None
    )
    assert seen == []
