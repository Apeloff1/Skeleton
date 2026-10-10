"""Discovery adapter tests with deterministic offline API fixtures."""
from urllib.parse import urlsplit
import pytest

from skeleton.ai.webcrawler.dragon_research_discovery import (
    DiscoveryQuery, ResearchSource, discover_research,
)


def fake_transport(url):
    host = urlsplit(url).hostname
    if host == "en.wikipedia.org":
        return {"pages": [
            {"id": 42, "title": "Quantum theory", "key": "Quantum_theory",
             "excerpt": "Scientific explanation"},
        ]}
    if host == "api.crossref.org":
        return {"message": {"items": [
            {"DOI": "10.1234/test.2025", "title": ["A journal paper"],
             "published": {"date-parts": [[2025, 5, 2]]},
             "abstract": "<jats:p>Evidence</jats:p>"},
            {"DOI": "invalid", "title": ["Rejected"]},
        ]}}
    if host == "api.openalex.org":
        return {"results": [
            {"id": "https://openalex.org/W123", "display_name": "Open study",
             "publication_year": 2024},
        ]}
    if host == "www.ebi.ac.uk":
        return {"resultList": {"result": [
            {"id": "123456", "title": "Clinical evidence", "pubYear": "2023"},
        ]}}
    if host == "nominatim.openstreetmap.org":
        return {"features": [
            {"properties": {"osm_id": 9, "osm_type": "node",
                            "name": "Museum"},
             "geometry": {"type": "Point", "coordinates": [5.32, 60.39]}},
        ]}
    raise AssertionError("unexpected host " + str(host))


def test_all_five_discovery_sources():
    result = discover_research(
        DiscoveryQuery("quantum research museum",
                       sources=tuple(ResearchSource)),
        fake_transport, authorized=True,
    )
    assert not result.errors
    assert len(result.hits) == 5
    assert {hit.source for hit in result.hits} == set(ResearchSource)
    assert next(hit for hit in result.hits
                if hit.source is ResearchSource.OPENSTREETMAP).coordinates == (
                    60.39, 5.32,
                )


def test_repeatable_receipts():
    query = DiscoveryQuery("quantum research",
                           sources=tuple(ResearchSource))
    a = discover_research(query, fake_transport, authorized=True)
    b = discover_research(query, fake_transport, authorized=True)
    assert a == b


def test_explicit_consent_is_required():
    with pytest.raises(PermissionError):
        discover_research(DiscoveryQuery("biology"), fake_transport,
                          authorized=False)


def test_query_and_budget_are_bounded():
    with pytest.raises(ValueError):
        discover_research(DiscoveryQuery("x"), fake_transport, authorized=True)
    with pytest.raises(ValueError):
        discover_research(DiscoveryQuery("science", limit_per_source=500),
                          fake_transport, authorized=True)


def test_source_errors_are_isolated():
    def failing_transport(url):
        if "crossref" in url:
            raise OSError("temporary outage")
        return fake_transport(url)
    result = discover_research(
        DiscoveryQuery("biology", sources=(
            ResearchSource.WIKIPEDIA, ResearchSource.CROSSREF,
        )), failing_transport, authorized=True,
    )
    assert len(result.hits) == 1
    assert result.errors == ("crossref: OSError",)


def test_journal_markup_is_not_preserved_as_html():
    result = discover_research(
        DiscoveryQuery("biology", sources=(ResearchSource.CROSSREF,)),
        fake_transport, authorized=True,
    )
    assert result.hits[0].abstract == "Evidence"
    assert result.hits[0].published_year == 2025
