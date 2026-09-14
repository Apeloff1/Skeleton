from __future__ import annotations

import asyncio
import hashlib

import httpx

from services.live_scrapers import SIZE_CAP, _polite_get, _stable_id, _validated_scraper_url


def test_stable_id_uses_sha256_prefix():
    expected = hashlib.sha256(b"unity-blog|https://example.test/item").hexdigest()[:18]
    assert _stable_id("unity-blog", "https://example.test/item") == expected


def test_scraper_url_blocks_non_https_and_non_curated_hosts():
    assert _validated_scraper_url("http://blog.unity.com/feed") is None
    assert _validated_scraper_url("https://127.0.0.1/admin") is None
    assert _validated_scraper_url("https://localhost/admin") is None
    assert _validated_scraper_url("https://example.com/feed") is None


def test_scraper_url_accepts_curated_https_host():
    validated = _validated_scraper_url("https://github.com/trending?since=daily")
    assert validated == ("https://github.com/trending?since=daily", "github.com")


def test_polite_get_rejects_declared_oversize_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "github.com"
        return httpx.Response(
            200,
            headers={"content-length": str(SIZE_CAP + 1)},
            content=b"small",
            request=request,
        )

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, follow_redirects=False) as client:
            return await _polite_get(client, "https://github.com/trending")

    assert asyncio.run(run()) is None


def test_polite_get_never_requests_blocked_host():
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, content=b"unexpected", request=request)

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, follow_redirects=False) as client:
            return await _polite_get(client, "https://localhost/internal")

    assert asyncio.run(run()) is None
    assert called is False
