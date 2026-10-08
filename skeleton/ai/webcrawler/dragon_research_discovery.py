"""Research discovery adapters for encyclopedias, scholarly journals and places.

Discovery uses public, documented JSON APIs rather than unrestricted HTML
scraping. A caller supplies the HTTP transport and must enforce DNS/IP
validation, robots/terms, rate limits, redirects, timeouts and egress policy.
No requests are made on import. API metadata is not treated as verified truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from typing import Callable, Mapping
from urllib.parse import urlencode, urlsplit
import json
import re


class ResearchSource(str, Enum):
    WIKIPEDIA = "wikipedia"
    CROSSREF = "crossref"
    OPENALEX = "openalex"
    EUROPE_PMC = "europe_pmc"
    OPENSTREETMAP = "openstreetmap"


@dataclass(frozen=True)
class ResearchHit:
    source: ResearchSource
    identifier: str
    title: str
    url: str
    abstract: str
    published_year: int | None
    coordinates: tuple[float, float] | None
    source_record: str


@dataclass(frozen=True)
class DiscoveryQuery:
    terms: str
    sources: tuple[ResearchSource, ...] = (
        ResearchSource.WIKIPEDIA,
        ResearchSource.CROSSREF,
        ResearchSource.OPENALEX,
        ResearchSource.EUROPE_PMC,
    )
    limit_per_source: int = 10
    language: str = "en"


@dataclass(frozen=True)
class DiscoveryReceipt:
    hits: tuple[ResearchHit, ...]
    rejected: int
    errors: tuple[str, ...]
    fingerprint: str


# HTTP clients are injected so this component is deterministic and testable.
# They MUST return decoded JSON for the exact URL, without arbitrary redirects.
JsonTransport = Callable[[str], Mapping[str, object]]
_ALLOWED_LANGUAGES = frozenset({"en", "de", "fr", "es", "it", "no", "nb", "nn", "sv", "da"})
_DOI = re.compile(r"^10\.\d{4,9}/\S+$", re.I)


def _plain(value: object, limit: int = 500) -> str:
    if not isinstance(value, str):
        return ""
    text = re.sub(r"<[^>]{0,500}>", " ", value)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _year(value: object) -> int | None:
    try:
        number = int(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return number if 1400 <= number <= 2200 else None


def _hit(source: ResearchSource, identifier: object, title: object,
         url: object, abstract: object = "", year: object = None,
         coordinates: tuple[float, float] | None = None) -> ResearchHit | None:
    ident = _plain(identifier, 250)
    name = _plain(title, 500)
    address = _plain(url, 1500)
    if not ident or not name or not address:
        return None
    parsed = urlsplit(address)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return None
    if parsed.hostname in {"localhost", "127.0.0.1"}:
        return None
    canonical = json.dumps([source.value, ident, address], separators=(",", ":"))
    return ResearchHit(source, ident, name, address, _plain(abstract, 2000),
                       _year(year), coordinates,
                       sha256(canonical.encode()).hexdigest())


def _records(source: ResearchSource, payload: Mapping[str, object]) -> list[ResearchHit]:
    results: list[ResearchHit] = []
    if source is ResearchSource.WIKIPEDIA:
        pages = payload.get("pages", [])
        if not isinstance(pages, list):
            return []
        for page in pages:
            if not isinstance(page, dict):
                continue
            item = _hit(source, str(page.get("id", "")), page.get("title"),
                        page.get("key") and "https://en.wikipedia.org/wiki/" +
                        str(page["key"]).replace(" ", "_"),
                        page.get("excerpt", ""))
            if item:
                results.append(item)
    elif source is ResearchSource.CROSSREF:
        message = payload.get("message", {})
        items = message.get("items", []) if isinstance(message, dict) else []
        for row in items if isinstance(items, list) else []:
            if not isinstance(row, dict):
                continue
            doi = row.get("DOI", "")
            if not isinstance(doi, str) or not _DOI.fullmatch(doi):
                continue
            titles = row.get("title", [])
            title = titles[0] if isinstance(titles, list) and titles else ""
            date = row.get("published", {})
            parts = date.get("date-parts", []) if isinstance(date, dict) else []
            year = parts[0][0] if parts and isinstance(parts[0], list) and parts[0] else None
            item = _hit(source, doi, title, "https://doi.org/" + doi,
                        row.get("abstract", ""), year)
            if item:
                results.append(item)
    elif source is ResearchSource.OPENALEX:
        rows = payload.get("results", [])
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            item = _hit(source, row.get("id"), row.get("display_name"),
                        row.get("doi") or row.get("id"),
                        "", row.get("publication_year"))
            if item:
                results.append(item)
    elif source is ResearchSource.EUROPE_PMC:
        rows = payload.get("resultList", {})
        rows = rows.get("result", []) if isinstance(rows, dict) else []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            pmid = str(row.get("id", ""))
            item = _hit(source, pmid, row.get("title"),
                        "https://europepmc.org/article/MED/" + pmid,
                        row.get("abstractText", ""), row.get("pubYear"))
            if item:
                results.append(item)
    elif source is ResearchSource.OPENSTREETMAP:
        rows = payload.get("features", [])
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            properties = row.get("properties", {})
            geometry = row.get("geometry", {})
            if not isinstance(properties, dict) or not isinstance(geometry, dict):
                continue
            coordinates = geometry.get("coordinates")
            location = None
            if (geometry.get("type") == "Point" and isinstance(coordinates, list)
                    and len(coordinates) >= 2):
                try:
                    longitude, latitude = float(coordinates[0]), float(coordinates[1])
                    if -180 <= longitude <= 180 and -90 <= latitude <= 90:
                        location = (latitude, longitude)
                except (TypeError, ValueError, OverflowError):
                    pass
            ident = properties.get("osm_id")
            kind = properties.get("osm_type", "node")
            item = _hit(source, str(ident) if ident is not None else "",
                        properties.get("name"),
                        f"https://www.openstreetmap.org/{kind}/{ident}",
                        properties.get("description", ""), coordinates=location)
            if item:
                results.append(item)
    return results


def _url(source: ResearchSource, query: DiscoveryQuery) -> str:
    terms = query.terms
    n = query.limit_per_source
    if source is ResearchSource.WIKIPEDIA:
        return (f"https://{query.language}.wikipedia.org/w/rest.php/v1/search/page?"
                + urlencode({"q": terms, "limit": n}))
    if source is ResearchSource.CROSSREF:
        return "https://api.crossref.org/works?" + urlencode({"query": terms, "rows": n})
    if source is ResearchSource.OPENALEX:
        return "https://api.openalex.org/works?" + urlencode({"search": terms, "per-page": n})
    if source is ResearchSource.EUROPE_PMC:
        return "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + urlencode({
            "query": terms, "format": "json", "pageSize": n,
        })
    if source is ResearchSource.OPENSTREETMAP:
        # Public Nominatim is not a bulk crawler; caller must comply with its
        # usage policy and supply identifying User-Agent/contact headers.
        return "https://nominatim.openstreetmap.org/search?" + urlencode({
            "q": terms, "format": "geojson", "limit": n,
        })
    raise ValueError("unsupported discovery source")


def discover_research(query: DiscoveryQuery, transport: JsonTransport, *,
                      authorized: bool, max_total: int = 100) -> DiscoveryReceipt:
    if not authorized:
        raise PermissionError("research discovery requires explicit authorization")
    if not isinstance(query.terms, str) or not 2 <= len(query.terms.strip()) <= 240:
        raise ValueError("invalid search terms")
    if query.language not in _ALLOWED_LANGUAGES:
        raise ValueError("unsupported encyclopedia language")
    if not 1 <= query.limit_per_source <= 25 or not 1 <= max_total <= 250:
        raise ValueError("invalid discovery budget")
    if len(query.sources) > 5 or len(set(query.sources)) != len(query.sources):
        raise ValueError("invalid source selection")
    if any(not isinstance(source, ResearchSource) for source in query.sources):
        raise ValueError("unknown source")
    hits: dict[tuple[str, str], ResearchHit] = {}
    errors: list[str] = []
    rejected = 0
    for source in query.sources:
        try:
            payload = transport(_url(source, query))
            if not isinstance(payload, dict):
                raise ValueError("invalid JSON response")
            records = _records(source, payload)
            for item in records[:query.limit_per_source]:
                key = (item.source.value, item.identifier)
                if key in hits:
                    rejected += 1
                else:
                    hits[key] = item
        except (ValueError, TypeError, KeyError, OSError) as exc:
            errors.append(f"{source.value}: {type(exc).__name__}")
    ordered = tuple(sorted(hits.values(), key=lambda item: (
        item.source.value, item.identifier,
    )))[:max_total]
    fingerprint = sha256(json.dumps([
        (item.source.value, item.identifier, item.source_record) for item in ordered
    ], separators=(",", ":")).encode()).hexdigest()
    return DiscoveryReceipt(ordered, rejected, tuple(errors), fingerprint)
