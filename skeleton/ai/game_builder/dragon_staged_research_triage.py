"""Task-focused, host-diverse triage for unapproved Dragon catalog observations.

This ranks metadata-only candidate URLs already validated against the
append-only discovery chain. It DOES NOT resolve network hosts, check current
rights, establish source independence, grant crawler jobs, or add knowledge.
"""
from __future__ import annotations

from collections import defaultdict
import re
from urllib.parse import urlsplit

from .contracts import canonical_digest
from .dragon_staged_supplements import build_catalog_supplements
from .dragon_source_catalog import canonical_source_url

_TERM = re.compile(r"[a-z0-9]+")
_MAX_TERMS = 16
_MAX_ITEMS = 100


def rank_staged_research_leads(
    registry: dict, accepted: list[tuple[str, dict]], stage: dict, *,
    task_terms: tuple[str, ...], first_batch: int,
    limit: int = 40, batch_size: int = 600,
) -> dict:
    """Generate review-only leads balanced across declared host identities.

    Input terms MUST reflect the human's live game-building task. Semantic
    quality, source independence and current content are never inferred from
    README links alone. All catalog observations pass the existing source
    discovery-chain validator before any ranked data is shown.
    """
    if (type(task_terms) is not tuple or not 1 <= len(task_terms) <= _MAX_TERMS
            or len(set(task_terms)) != len(task_terms)
            or any(type(v) is not str
                   or not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,39}", v)
                   for v in task_terms)):
        raise ValueError("bounded unique canonical task terms required")
    if type(limit) is not int or not 1 <= limit <= _MAX_ITEMS:
        raise ValueError("bounded positive candidate review limit required")
    plan = build_catalog_supplements(
        registry, accepted, stage, first_batch=first_batch,
        batch_size=batch_size,
    )
    ranked = []
    for name, document in plan["supplements"]:
        for candidate in document["candidates"]:
            raw = candidate["url"]
            host = urlsplit(canonical_source_url(raw)).hostname
            provenance = candidate["discoveries"]
            if not host or not provenance:
                raise ValueError("canonical observed host and provenance required")
            # Only the exact terms visible in URL and observed README
            # headings are scored. No fetched source text is available here.
            tokens = set(_TERM.findall(raw.casefold()))
            tokens.update(t for obs in provenance
                          for h in obs["headers"]
                          for t in _TERM.findall(h.casefold()))
            matched = sorted(set(task_terms) & tokens)
            # Multiple links in the same repository/commit are not independent
            # corroboration. Retain the count only as a catalog navigation hint.
            claims = {
                (o["repository"], o["commit_sha"], o["readme_blob_sha"])
                for o in provenance
            }
            signal = len(matched) * 10 + min(len(provenance), 5)
            ranked.append({
                "source_id": candidate["source_id"],
                "url": raw,
                "host": host,
                "batch": name,
                "task_terms_matched": matched,
                "lexical_relevance_signal": signal,
                "observations": len(provenance),
                "git_catalog_claims": len(claims),
                "catalog_identity_verified": False,
                "content_verified": False,
                "independent_sources_verified": False,
                "rights_approved": False,
                "crawler_authorized": False,
                "training_authorized": False,
                "xp_awarded": 0,
            })
    ranked.sort(key=lambda x: (-x["lexical_relevance_signal"],
                               x["host"], x["url"], x["source_id"]))
    # Interleave hosts while respecting deterministic descending relevance
    # within each host. No host can monopolize the first triage round.
    buckets = defaultdict(list)
    for row in ranked:
        buckets[row["host"]].append(row)
    order = sorted(buckets, key=lambda host: (
        -buckets[host][0]["lexical_relevance_signal"], host))
    chosen = []
    while len(chosen) < limit and order:
        next_order = []
        for host in order:
            if len(chosen) >= limit:
                break
            chosen.append(buckets[host].pop(0))
            if buckets[host]:
                next_order.append(host)
        order = next_order
    core = {
        "schema": "skeleton.dragon.metadata_research_triage.v1",
        "task_terms": list(task_terms),
        "candidate_urls_from_staging": len(ranked),
        "candidate_urls_in_page": len(chosen),
        "unique_observed_hosts": len(buckets),
        "source_observations": plan["staged_observations"],
        "candidates": chosen,
        "truncated": len(chosen) < len(ranked),
        "host_diversity_only_not_source_independence": True,
        "research_review_only": True,
        "rights_approved": False,
        "network_requests": 0,
        "crawler_authorized": False,
        "training_authorized": False,
        "xp_awarded": 0,
    }
    return {**core, "triage_digest": canonical_digest(core)}
