"""Offline public-API selector and fixed-host transport admission regressions."""
from __future__ import annotations

import pytest

from gameforge.knowledge import free_apis as catalog


@pytest.mark.parametrize("bad", [
    "", " " * 512, "x" * 513, None, True, 10, ["unknown"], {},
])
def test_selector_denies_unbounded_or_nontext_queries(bad):
    with pytest.raises(ValueError, match="query"):
        catalog.pick_api(bad)


@pytest.mark.parametrize("text,expected", [
    ("define ephemeral", "dictionary"),
    ("synonyms for durable", "datamuse"),
    ("papers about cryptography", "arxiv"),
    ("GitHub repos for Python", "github"),
    ("country Iceland", "countries"),
    ("what is a galaxy", "wikipedia"),
])
def test_fixed_api_selector_remains_functional_with_bounded_text(text, expected):
    key, parameters = catalog.pick_api(text)
    assert key == expected
    assert isinstance(parameters, dict) and "q" in parameters
    assert len(parameters["q"]) <= 512


@pytest.mark.parametrize("malicious", [
    "http://en.wikipedia.org/api/rest_v1/page/summary/test",
    "https://en.wikipedia.org.attacker.test/path",
    "https://somebody@en.wikipedia.org/path",
    "https://somebody:password@en.wikipedia.org/path",
    "https://en.wikipedia.org:8443/path",
    "https://127.0.0.1/path",
    "https://en.wikipedia.org/path#fragment",
    "https://en.wikipedia.org\\@evil.test/path",
])
def test_catalog_fixed_origin_refuses_deceptive_urls(malicious):
    with pytest.raises(ValueError):
        catalog._validate_catalog_url(catalog.FREE_APIS["wikipedia"], malicious)


def test_caller_query_is_quoted_and_never_becomes_url_authority():
    api = catalog.FREE_APIS["wikipedia"]
    url = catalog._build_url(api, {"q": "https://127.0.0.1:9000/?secret=private"})
    origin, target = catalog._catalog_request_parts(api, url)
    assert origin == "https://en.wikipedia.org"
    assert target.startswith("/api/rest_v1/page/summary/")
    assert "127.0.0.1" in target
    assert target.startswith("/api/")
    assert target.find("?secret=") == -1
