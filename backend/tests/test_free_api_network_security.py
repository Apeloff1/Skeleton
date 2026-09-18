from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlsplit

import pytest

from gameforge.knowledge import free_apis


class _FakeResponse:
    def __init__(self, chunks: list[bytes], headers: dict[str, str] | None = None):
        self._chunks = chunks
        self.headers = headers or {}

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk


def test_placeholder_values_are_percent_encoded_as_data() -> None:
    url = free_apis._build_url(
        free_apis.FREE_APIS["github"],
        {"q": "safe&per_page=100#fragment"},
    )
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)

    assert parsed.hostname == "api.github.com"
    assert parsed.fragment == ""
    assert query["q"] == ["safe&per_page=100#fragment"]
    assert query["per_page"] == ["5"]


def test_extra_parameters_are_query_encoded() -> None:
    url = free_apis._build_url(
        free_apis.FREE_APIS["trivia"],
        {"filter": "x&admin=true#fragment"},
    )
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)

    assert parsed.hostname == "opentdb.com"
    assert parsed.fragment == ""
    assert query["amount"] == ["5"]
    assert query["filter"] == ["x&admin=true#fragment"]


def test_declared_oversized_response_is_rejected() -> None:
    response = _FakeResponse(
        [b"x"],
        {"content-length": str(free_apis._MAX_RESPONSE_BYTES + 1)},
    )

    with pytest.raises(ValueError, match="size limit"):
        asyncio.run(free_apis._read_bounded_body(response))


def test_malformed_content_length_fails_closed() -> None:
    response = _FakeResponse([b"x"], {"content-length": "not-a-number"})

    with pytest.raises(ValueError, match="content length"):
        asyncio.run(free_apis._read_bounded_body(response))


def test_streamed_oversized_response_is_rejected_without_length() -> None:
    response = _FakeResponse(
        [b"x" * free_apis._MAX_RESPONSE_BYTES, b"y"],
    )

    with pytest.raises(ValueError, match="size limit"):
        asyncio.run(free_apis._read_bounded_body(response))


def test_bounded_response_is_returned_exactly() -> None:
    response = _FakeResponse([b'{"ok":', b"true}"])

    assert asyncio.run(free_apis._read_bounded_body(response)) == b'{"ok":true}'
