"""Offline regressions for shared outbound admission and transport custody."""
from __future__ import annotations

import asyncio
import ipaddress
import threading
from contextlib import asynccontextmanager

import httpx
import pytest

from gameforge import egress_admission as admission
from gameforge.knowledge import free_apis as catalog
from gameforge.rooms import room_api_gateway as rooms


@pytest.mark.parametrize("capacity", [0, -1, True, 65, 1.5, "2"])
def test_invalid_dns_capacity(capacity):
    with pytest.raises(ValueError, match="capacity"):
        admission.BoundedResolver(capacity)


@pytest.mark.parametrize("timeout", [0, -1, True, float("nan"), float("inf"), 31, 10**400])
def test_bad_timeout_never_submits_work(timeout):
    async def scenario():
        with pytest.raises(ValueError, match="timeout"):
            await admission.BoundedResolver(1).run(
                lambda: pytest.fail("invalid deadline submitted work"), timeout=timeout
            )
    asyncio.run(scenario())


@pytest.mark.parametrize("cancel", [False, True])
def test_abandoned_caller_does_not_release_physical_work(cancel):
    async def scenario():
        resolver = admission.BoundedResolver(1)
        started, release = threading.Event(), threading.Event()

        def blocked():
            started.set()
            if not release.wait(5):
                raise RuntimeError("test resolver was not released")
            return "late"

        task = asyncio.create_task(resolver.run(blocked, timeout=2 if cancel else 0.3))
        try:
            assert await asyncio.to_thread(started.wait, 1)
            if cancel:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                with pytest.raises(TimeoutError):
                    await task
            for _ in range(32):
                with pytest.raises(admission.ResolverCapacityError):
                    await resolver.run(lambda: pytest.fail("queued abandoned work"))
        finally:
            release.set()
            if not task.done():
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
        deadline = asyncio.get_running_loop().time() + 2
        while True:
            try:
                assert await resolver.run(lambda: "recovered") == "recovered"
                break
            except admission.ResolverCapacityError:
                if asyncio.get_running_loop().time() >= deadline:
                    pytest.fail("physical worker never returned its permit")
                await asyncio.sleep(0.005)
    asyncio.run(scenario())


def test_worker_failure_returns_permit():
    async def scenario():
        resolver = admission.BoundedResolver(1)

        def fail():
            raise OSError("offline")

        with pytest.raises(OSError, match="offline"):
            await resolver.run(fail)
        assert await resolver.run(lambda: 42) == 42
    asyncio.run(scenario())


def test_http_slot_releases_on_error():
    pool = admission.EgressAdmission(1)
    with pytest.raises(RuntimeError, match="operation failed"):
        with pool.slot():
            with pytest.raises(admission.EgressCapacityError):
                with pool.slot():
                    pytest.fail("second exchange admitted")
            raise RuntimeError("operation failed")
    with pool.slot():
        pass


def test_http_slot_releases_on_cancel():
    async def scenario():
        pool = admission.EgressAdmission(1)
        started = asyncio.Event()

        async def request():
            with pool.slot():
                started.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(request())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pool.slot():
            pass
    asyncio.run(scenario())


@pytest.mark.parametrize("address", [
    "127.0.0.1", "10.1.2.3", "169.254.169.254", "224.0.0.1",
    "240.0.0.1", "::1", "fe80::1", "ff02::1", "2002:0808:0808::1",
    "::ffff:8.8.8.8", "2606:4700:4700::1111%eth0",
])
def test_nonpublic_or_nonunicast_addresses_denied(address):
    assert not admission.is_public_egress_address(ipaddress.ip_address(address))


@pytest.mark.parametrize("address", ["8.8.8.8", "2606:4700:4700::1111"])
def test_public_unicast_allowed(address):
    assert admission.is_public_egress_address(ipaddress.ip_address(address))


class Response:
    def __init__(self, headers, chunks=()):
        self.headers = headers
        self.chunks = chunks
        self.read = False

    async def aiter_bytes(self):
        self.read = True
        for chunk in self.chunks:
            yield chunk


@pytest.mark.parametrize("reader", [rooms._bounded_http_body, catalog._read_bounded_body])
@pytest.mark.parametrize("headers", [
    {"content-encoding": "gzip"}, {"content-encoding": "br"},
    {"content-length": "-1"}, {"content-length": "1e8"},
    {"content-length": "9999999999999"}, {"content-length": "99999999"},
])
def test_reject_bad_response_before_body_read(reader, headers):
    response = Response(headers, [b"do not read"])
    with pytest.raises(ValueError):
        asyncio.run(reader(response))
    assert not response.read


@pytest.mark.parametrize("reader", [rooms._bounded_http_body, catalog._read_bounded_body])
def test_reject_nonbyte_chunk(reader):
    with pytest.raises(ValueError):
        asyncio.run(reader(Response({}, ["wrong type"])))


def test_catalog_total_deadline_bounds_slow_drip(monkeypatch):
    monkeypatch.setattr(catalog, "_MAX_HTTP_SECONDS", 0.05)
    monkeypatch.setattr(catalog, "_pin_public_origin", lambda host: "https://8.8.8.8")
    pool = admission.EgressAdmission(1)
    monkeypatch.setattr(catalog, "HTTP_ADMISSION", pool)

    class SlowResponse(Response):
        status_code, is_success = 200, True

        async def aiter_bytes(self):
            for _ in range(20):
                await asyncio.sleep(0.01)
                yield b"x"

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False
            assert kwargs["trust_env"] is False
            assert kwargs["headers"]["Accept-Encoding"] == "identity"
            assert kwargs["base_url"] == "https://8.8.8.8"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        @asynccontextmanager
        async def stream(self, method, target, **kwargs):
            assert target.startswith("/") and not target.startswith("//")
            assert kwargs["extensions"]["sni_hostname"] == "en.wikipedia.org"
            yield SlowResponse({})

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    result = asyncio.run(catalog.fetch("wikipedia", {"q": "test"}))
    assert result["ok"] is False and result["error"] == "api_fetch_failed"
    with pool.slot():
        pass


def test_room_and_catalog_share_global_http_capacity(monkeypatch):
    assert rooms.HTTP_ADMISSION is catalog.HTTP_ADMISSION
    monkeypatch.setattr(rooms, "_EXTERNAL_ENABLED", True)
    pool = admission.EgressAdmission(1)
    monkeypatch.setattr(rooms, "HTTP_ADMISSION", pool)
    monkeypatch.setattr(catalog, "HTTP_ADMISSION", pool)

    def never(*_):
        pytest.fail("saturated admission triggered DNS")

    monkeypatch.setattr(rooms, "_prepare_external_request", never)
    monkeypatch.setattr(catalog, "_pin_public_origin", never)
    with pool.slot():
        a = asyncio.run(rooms._api_query({"url": "https://example.com/"}))
        b = asyncio.run(catalog.fetch("wikipedia", {}))
    assert a["ok"] is False
    assert b["ok"] is False


def test_room_rejects_caller_compression_override():
    with pytest.raises(ValueError):
        rooms._safe_headers({"accept-encoding": "gzip"})


@pytest.mark.parametrize("api_key", [None, [], {}, "", "x" * 65])
def test_invalid_catalog_key_is_structured(api_key):
    assert asyncio.run(catalog.fetch(api_key, {})) == {
        "ok": False, "error": "invalid_api_key"
    }
