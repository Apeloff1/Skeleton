from routes.share import _page


def test_share_page_escapes_markup_and_script_boundaries() -> None:
    payload = '"><img src=x onerror=alert(1)>'
    page = _page(
        payload,
        payload,
        f"https://cdn.example.invalid/{payload}",
        f"https://app.example.invalid/{payload}",
    )

    assert page.count("<script>") == 1
    assert '<img src=x onerror=alert(1)>' not in page
    assert '&lt;img src=x onerror=alert(1)&gt;' in page
    assert '\\u003cimg src=x onerror=alert(1)\\u003e' in page
    assert 'href="https://app.example.invalid/&quot;&gt;&lt;img' in page

import asyncio

import pytest
from starlette.requests import Request

from routes import share


def test_share_origin_does_not_trust_request_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUBLIC_APP_URL", "https://app.example.test/")
    assert share._app_origin() == "https://app.example.test"
    for bad in ("http://evil.example", "https://user:pass@app.example.test",
                "https://app.example.test/?next=evil", "https://app.example.test/path",
                "https://app.example.test\\\\@evil.test"):
        monkeypatch.setenv("PUBLIC_APP_URL", bad)
        with pytest.raises(ValueError):
            share._app_origin()


def test_production_origin_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PUBLIC_APP_URL", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(ValueError, match="PUBLIC_APP_URL"):
        share._app_origin()
    monkeypatch.setenv("PUBLIC_APP_URL", "http://localhost:3000")
    with pytest.raises(ValueError, match="HTTPS"):
        share._app_origin()
    monkeypatch.setenv("PUBLIC_APP_URL", "https://app.example.test?")
    with pytest.raises(ValueError, match="canonical origin"):
        share._app_origin()


def test_share_identifiers_are_encoded_as_one_component() -> None:
    encoded = share._safe_link_id("x?admin=true&#fragment")
    assert "?" not in encoded and "&" not in encoded and "#" not in encoded
    with pytest.raises(ValueError):
        share._safe_link_id("bad\nname")


def test_share_playable_uses_configured_origin_and_encoded_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Playables:
        async def find_one(self, _query, _projection):
            return {"title": "safe", "genre": "arcade", "plays": 0}
    class Database:
        playables = Playables()

    monkeypatch.setattr(share, "_db", Database())
    monkeypatch.setenv("PUBLIC_APP_URL", "https://app.example.test")
    request = Request({"type": "http", "method": "GET", "path": "/",
                       "headers": [(b"host", b"attacker.example")]})
    payload = "game&admin=true#fragment"
    response = asyncio.run(share.share_playable(payload, request))
    page = response.body.decode("utf-8")
    assert "attacker.example" not in page
    assert "/api/playable/game%26admin%3Dtrue%23fragment/cover.png" in page
    assert "playable?id=game%26admin%3Dtrue%23fragment" in page
    assert "playable?id=game&admin=true" not in page


def test_tournament_cover_link_encodes_champion_identifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Tournaments:
        async def find_one(self, _query, _projection):
            return {"name": "League", "champion_id": "player&admin=true"}
    class Database:
        tournaments = Tournaments()

    monkeypatch.setattr(share, "_db", Database())
    monkeypatch.setenv("PUBLIC_APP_URL", "https://app.example.test")
    request = Request({"type": "http", "method": "GET", "path": "/",
                       "headers": [(b"host", b"attacker.example")]})
    response = asyncio.run(share.share_tournament("spring", request))
    page = response.body.decode("utf-8")
    assert "/api/playable/player%26admin%3Dtrue/cover.png" in page
    assert "attacker.example" not in page
