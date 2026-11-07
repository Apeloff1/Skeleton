"""OPDS 2 catalog navigation, without downloading publications or DRM data."""
from __future__ import annotations

from .archive_catalog_common import (
    MAX_ENTRIES, CatalogDiscoveryError, CatalogLinks,
    LinkCollector, catalog_source, load_json_catalog,
)
from .core import CrawlPolicy

OPDS_TYPES = frozenset({"application/opds+json"})
_CATALOG_MIMES = frozenset({
    "application/opds+json", "application/opds+json;profile=navigation",
})
_NAV_REL = frozenset({"next", "prev", "first", "subsection"})


def _rel(value: object) -> frozenset[str]:
    if not isinstance(value, str) or len(value) > 128:
        return frozenset()
    return frozenset(value.casefold().split())


def _mime_type(value: object) -> str:
    if not isinstance(value, str) or len(value) > 128:
        raise CatalogDiscoveryError("unbounded or invalid OPDS link MIME type")
    return value.split(";", 1)[0].strip().casefold()


def discover_opds(
    body: bytes, *, document_url: str, policy: CrawlPolicy,
    max_links: int = 32, max_entries: int = 128,
) -> CatalogLinks:
    source = catalog_source(document_url, policy)
    if type(max_entries) is not int or not 1 <= max_entries <= MAX_ENTRIES:
        raise CatalogDiscoveryError("OPDS entry capacity invalid")
    root = load_json_catalog(body)
    metadata = root.get("metadata")
    links = root.get("links")
    if (not isinstance(metadata, dict) or not isinstance(metadata.get("title"), str)
            or not 0 < len(metadata["title"]) <= 512
            or not isinstance(links, list) or len(links) > MAX_ENTRIES):
        raise CatalogDiscoveryError("OPDS catalog metadata/links missing")
    # A publication catalog may contain sensitive annotations, auth URIs,
    # purchase/download action links, credentials or DRM URLs. Only explicit
    # links to other typed catalog endpoints may be nominated.
    publications = root.get("publications", [])
    navigation = root.get("navigation", [])
    if (not isinstance(publications, list) or len(publications) > max_entries
            or not isinstance(navigation, list) or len(navigation) > max_entries):
        raise CatalogDiscoveryError("OPDS publication/navigation cap exceeded")
    out = LinkCollector(source=source, policy=policy, max_links=max_links)
    for item in links:
        if not isinstance(item, dict):
            raise CatalogDiscoveryError("invalid OPDS navigation link object")
        if not (_rel(item.get("rel")) & _NAV_REL):
            continue
        if _mime_type(item.get("type", "")) != "application/opds+json":
            out.add(None)
            continue
        out.add(item.get("href"))
    for item in navigation:
        if not isinstance(item, dict):
            raise CatalogDiscoveryError("invalid OPDS navigation record")
        targets = item.get("links", [])
        if not isinstance(targets, list) or len(targets) > 64:
            raise CatalogDiscoveryError("invalid OPDS navigation target list")
        for link in targets:
            if not isinstance(link, dict):
                raise CatalogDiscoveryError("invalid OPDS navigation target")
            if _mime_type(link.get("type", "")) == "application/opds+json":
                out.add(link.get("href"))
    return out.report("opds_public_catalog")
