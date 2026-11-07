"""IIIF Presentation 3 Collection traversal without image service requests.

Only declared Collection and Manifest identities from a same-origin public
Collection are exposed as hints. Manifests are retained separately as
unreviewed source evidence rather than interpreted as download instructions.
Canvas, rendering, thumbnail, authentication, search, seeAlso and service URLs
never grant network authority.
"""
from __future__ import annotations

from .archive_catalog_common import (
    MAX_ENTRIES, CatalogDiscoveryError, CatalogAsDocument,
    CatalogLinks, LinkCollector, catalog_source, load_json_catalog,
)
from .core import CrawlPolicy

IIIF_TYPES = frozenset({"application/vnd.iiif.presentation+json"})
_CONTEXT = frozenset({
    "http://iiif.io/api/presentation/3/context.json",
    "https://iiif.io/api/presentation/3/context.json",
})
_CHILDREN = frozenset({"Manifest", "Collection"})


def discover_iiif(
    body: bytes, *, document_url: str, policy: CrawlPolicy,
    max_links: int = 32, max_entries: int = 128,
) -> CatalogLinks:
    source = catalog_source(document_url, policy)
    if type(max_entries) is not int or not 1 <= max_entries <= MAX_ENTRIES:
        raise CatalogDiscoveryError("IIIF collection item capacity invalid")
    doc = load_json_catalog(body)
    context = doc.get("@context")
    if not isinstance(context, str) or context not in _CONTEXT:
        raise CatalogDiscoveryError("unsupported or external IIIF context")
    kind = doc.get("type")
    if kind == "Manifest":
        raise CatalogAsDocument("IIIF Manifest is a retained source, not discovery")
    if kind != "Collection":
        raise CatalogDiscoveryError("only IIIF v3 Collection roots are navigable")
    items = doc.get("items")
    if not isinstance(items, list) or len(items) > max_entries:
        raise CatalogDiscoveryError("IIIF Collection item capacity exceeded")
    out = LinkCollector(source=source, policy=policy, max_links=max_links)
    for entry in items:
        if not isinstance(entry, dict):
            raise CatalogDiscoveryError("invalid IIIF collection entry")
        kind = entry.get("type")
        if isinstance(kind, str) and kind in _CHILDREN:
            out.add(entry.get("id"))
    for direction in ("next", "prev"):
        value = doc.get(direction)
        if isinstance(value, dict):
            value = value.get("id") if value.get("type") == "Collection" else None
        if value is not None:
            out.add(value)
    return out.report("iiif_public_collection")
