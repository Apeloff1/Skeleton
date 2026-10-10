"""Reproducible link discovery from retrieved catalogs, never crawl permission.

Public links are leads. Catalog inclusion does not establish accuracy, rights,
source independence, availability or permission to download a linked work.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import html
import ipaddress
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .contracts import canonical_digest
from .reviewed_knowledge import _text, _utc


def canonical_source_url(value: str) -> str:
    _text(value, "source URL", 2048)
    if any(c.isspace() for c in value):
        raise ValueError("URL whitespace must be encoded")
    p = urlsplit(html.unescape(value))
    host = (p.hostname or "").lower().rstrip(".")
    if p.scheme not in ("https", "http") or p.username or p.password or p.port not in (None, 80, 443):
        raise ValueError("public HTTP source URL required")
    if not host or "." not in host or host.endswith((".local", ".internal", ".localhost", ".test", ".invalid")):
        raise ValueError("public hostname required")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None:
        raise ValueError("IP literals are not catalog sources")
    # DNS and every redirect still require the canonical runtime's SSRF checks.
    if not re.fullmatch(r"[a-z0-9.-]+", host):
        raise ValueError("canonical ASCII hostname required")
    if any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in host.split(".")):
        raise ValueError("invalid hostname label")
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
    return urlunsplit((p.scheme, host, p.path or "/", urlencode(query), ""))


def _links(line: str):
    for match in re.finditer(r"https?://[^\s<>\"\]]+", line):
        value = match.group().rstrip(".,;!`")
        while value.endswith(")") and value.count(")") > value.count("("):
            value = value[:-1]
        yield value


def extract_catalog(content: str, *, catalog_url: str, blob_sha: str,
                    observed_at: str) -> dict:
    """Extract URLs and heading lineage without copying article descriptions."""
    if not isinstance(content, str) or len(content) > 2_000_000:
        raise ValueError("bounded catalog text required")
    _text(content.strip().replace("\r\n", "\n"), "catalog", 2_000_000)
    catalog_url = canonical_source_url(catalog_url)
    _utc(observed_at)
    if not isinstance(blob_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", blob_sha):
        raise ValueError("retrieved Git blob identity required")
    catalog_id = "catalog-" + blob_sha
    manifest = {"catalog_id": catalog_id, "url": catalog_url,
                "git_blob_sha": blob_sha, "content_sha256": sha256(content.encode()).hexdigest(),
                "observed_at": observed_at, "linked_content_fetched": False}
    headings = []
    rows = {}
    rejected = 0
    for line_number, line in enumerate(content.splitlines(), 1):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if match:
            level, title = len(match[1]), match[2][:160]
            while headings and headings[-1][0] >= level:
                headings.pop()
            headings.append((level, title))
        for candidate in _links(line):
            try:
                url = canonical_source_url(candidate)
            except ValueError:
                rejected += 1
                continue
            p = urlsplit(url)
            if (p.hostname in {"img.shields.io", "badges.gitter.im", "opencollective.com"}
                    or p.path.lower().endswith((".png", ".jpg", ".gif", ".svg", ".webp"))
                    or "/actions/workflows/" in p.path):
                continue
            identity = "source-" + sha256(url.encode()).hexdigest()
            provenance = {"catalog_id": catalog_id, "line": line_number,
                          "headers": [h[1] for h in headings] or ["Uncategorized"]}
            row = rows.setdefault(url, {"source_id": identity, "url": url,
                "host": p.hostname, "kind": "video_candidate" if p.hostname in
                    {"youtube.com", "www.youtube.com", "youtu.be", "vimeo.com", "www.vimeo.com"}
                    else "web_candidate", "discoveries": [],
                "availability": "not_checked", "rights": "not_assessed",
                "independence": "not_assessed", "training_authorized": False})
            if provenance not in row["discoveries"]:
                row["discoveries"].append(provenance)
    return {"manifest": manifest, "sources": sorted(rows.values(), key=lambda x: x["source_id"]),
            "rejected_url_count": rejected}


def merge_catalogs(catalogs: list[dict]) -> dict:
    if not isinstance(catalogs, list) or not 1 <= len(catalogs) <= 128:
        raise ValueError("bounded retrieved catalogs required")
    merged = {}
    manifests = {}
    for catalog in catalogs:
        manifest = catalog["manifest"]
        cid = manifest["catalog_id"]
        if cid in manifests and manifests[cid] != manifest:
            raise ValueError("conflicting catalog identity")
        manifests[cid] = manifest
        for item in catalog["sources"]:
            url = canonical_source_url(item["url"])
            if item["source_id"] != "source-" + sha256(url.encode()).hexdigest():
                raise ValueError("source identity mismatch")
            if url not in merged:
                merged[url] = {**item, "discoveries": []}
            for origin in item["discoveries"]:
                if origin not in merged[url]["discoveries"]:
                    merged[url]["discoveries"].append(origin)
            if len(merged) > 100_000:
                raise ValueError("catalog source budget exceeded")
    sources = sorted(merged.values(), key=lambda x: x["source_id"])
    for row in sources:
        row["discoveries"].sort(key=lambda x: (x["catalog_id"], x["line"]))
    body = {"schema": "skeleton.dragon.source_catalog.v1",
            "catalogs": sorted(manifests.values(), key=lambda x: x["catalog_id"]),
            "sources": sources, "unique_urls": len(sources),
            "unique_hosts": len({r["host"] for r in sources}),
            "kinds": dict(sorted(Counter(r["kind"] for r in sources).items())),
            "coverage": "discovered_catalog_links_not_exhaustive_web_inventory",
            "individually_fetched_sources": 0, "approved_sources": 0}
    return {**body, "catalog_digest": canonical_digest(body)}
