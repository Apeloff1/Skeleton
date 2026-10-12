"""Reproducible statistics over strictly checked Dragon source-discovery evidence.

All counts are metadata counts, not factual corroboration, legality, rights,
network-fetch permission, reviewed knowledge or training/model improvement.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import re
from urllib.parse import urlsplit

from .dragon_discovery_admission import validate_discovery_chain
from .dragon_discovery_reconciled import _chain, SOURCE_BATCHES, EXPECTED_RAW_TOTAL
from .dragon_source_catalog import canonical_source_url


_RISK_TERMS = frozenset({
    "rom", "roms", "bios", "torrent", "warez", "keygen", "cracked",
    "piracy", "dumps", "dump", "iso", "firmware", "pirated",
})
_VIDEO_HOSTS = frozenset({
    "youtube.com", "www.youtube.com", "youtu.be", "vimeo.com",
    "www.vimeo.com", "video.google.com",
})
_SCHOLARLY_HOSTS = frozenset({
    "arxiv.org", "doi.org", "openreview.net", "aclanthology.org",
    "proceedings.mlr.press", "www.jmlr.org", "ieeexplore.ieee.org",
    "dl.acm.org",
})
_REPOSITORY_HOSTS = frozenset({
    "github.com", "gitlab.com", "codeberg.org", "bitbucket.org",
    "sourceforge.net", "www.sourceforge.net",
})


def _category(host: str) -> str:
    if host in _REPOSITORY_HOSTS:
        return "repository_link_candidate"
    if host in _VIDEO_HOSTS:
        return "video_metadata_candidate"
    if host in _SCHOLARLY_HOSTS:
        return "research_publication_link_candidate"
    if host.startswith("docs.") or host.endswith((".readthedocs.io", ".github.io")):
        return "documentation_link_candidate"
    return "other_web_link_candidate"


def discovery_census(registry: dict, *, top_hosts: int = 25) -> dict:
    """Full-corpus bounded inventory with neutral risk flags and host diversity.

    Rejects any interrupted, duplicate, forged, out-of-order, or unauthorized
    discovery chain before computing any statistics.
    """
    if type(top_hosts) is not int or not 1 <= top_hosts <= 100:
        raise ValueError("invalid top host count")
    chain = _chain()
    checked = validate_discovery_chain(registry, chain)
    if checked["raw_total_discovered"] != EXPECTED_RAW_TOTAL or len(chain) != len(SOURCE_BATCHES):
        raise ValueError("census evidence must match full frozen sequence")

    raw_by_host = Counter()
    canonical_by_host = Counter()
    categories = Counter()
    risk_hits = Counter()
    source_catalogs = defaultdict(set)
    observed_hosts = set()
    all_urls = [row["url"] for row in registry["sources"]]
    evidence_rows = []
    for path, document in chain:
        for candidate in document["candidates"]:
            all_urls.append(candidate["url"])
            evidence_rows.append((path, candidate))

    canonical_urls = set()
    for raw in all_urls:
        normalized = canonical_source_url(raw)
        host = urlsplit(normalized).hostname
        if not host:
            raise ValueError("canonical source without host")
        raw_by_host[host] += 1
        observed_hosts.add(host)
        if normalized not in canonical_urls:
            canonical_urls.add(normalized)
            canonical_by_host[host] += 1
            categories[_category(host)] += 1
        tokens = frozenset(re.findall(r"[a-z0-9]+", (
            host + " " + urlsplit(normalized).path).lower()))
        for term in sorted(tokens & _RISK_TERMS):
            risk_hits[term] += 1

    for _, candidate in evidence_rows:
        url = canonical_source_url(candidate["url"])
        for origin in candidate["discoveries"]:
            # Catalog occurrences are not independently reviewed original
            # content or verified factual corroboration.
            repo = origin.get("repository", origin.get("catalog_url", "unknown"))
            source_catalogs[repo].add(url)
    leaders = sorted(observed_hosts,
                     key=lambda host: (-canonical_by_host[host],
                                       -raw_by_host[host], host))[:top_hosts]
    if len(all_urls) != checked["raw_total_discovered"]:
        raise ValueError("evidence raw-count drift")
    if len(canonical_urls) != checked["total_discovered"]:
        raise ValueError("normalized source-count drift")
    return {
        "schema": "skeleton.dragon.discovery_source_census.v1",
        "source_of_truth": "frozen_reconciled_discovery_chain",
        "baseline_raw_leads": registry["unique_urls"],
        "supplement_raw_leads": checked["raw_new"],
        "raw_url_leads": len(all_urls),
        "canonical_distinct_urls": len(canonical_urls),
        "raw_to_canonical_collisions": len(all_urls) - len(canonical_urls),
        "unique_hosts": len(observed_hosts),
        "category_counts_canonical": dict(sorted(categories.items())),
        "rights_review_keyword_hits_raw": dict(sorted(risk_hits.items())),
        "top_hosts": [
            {"host": host, "raw_leads": raw_by_host[host],
             "canonical_urls": canonical_by_host[host],
             "percent_of_canonical_urls": round(
                 100 * canonical_by_host[host] / len(canonical_urls), 3)}
            for host in leaders
        ],
        "catalog_link_contributions": [
            {"catalog": name, "canonical_url_mentions": len(urls),
             "independently_corroborated": False}
            for name, urls in sorted(source_catalogs.items(),
                                     key=lambda item: (-len(item[1]), item[0]))
        ],
        "catalog_identity_is_pinned_claim_not_independent_attestation": True,
        "host_diversity_not_source_independence": True,
        "rights_keyword_hit_not_legal_finding": True,
        "crawler_authorized": False,
        "source_rights_approved": False,
        "training_authorized": False,
        "memory_promotion_authorized": False,
    }
