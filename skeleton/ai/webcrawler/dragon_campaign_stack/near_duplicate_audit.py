"""Policy-bound near-duplicate screening of currently selected Dragon sources.

This module compares exact source text already in the canonical CrawlRun
snapshot. It never fetches URLs, dereferences source links, writes results,
asserts shared authorship, treats text similarity as truth, or converts
unreviewed page instructions into executable authority.

Differences from exact-content duplicate detection:
  * Unicode NFKC/casefold normalization and bounded lexical four-shingles
    permit small editorial alterations to raise a human review lead;
  * per-source token, size, pair and candidate bounds are fail-closed;
  * unscorable sources are visible holds rather than assumed dissimilar;
  * pairwise evidence is retained even when a transitive cluster connects
    endpoints that were never directly similar.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from hashlib import sha256
from itertools import combinations
from math import isfinite
import re
import unicodedata
from urllib.parse import urlsplit

from ..operations import CrawlRun
from .contracts import CampaignMandate, digest, ensure_snapshot_scope, integer
from .policy_matrix import SourcePolicyProjection
from .retrieval_fusion import RetrievalFusion


_WORDS = re.compile(r"[^\W_]+", re.UNICODE)


@dataclass(frozen=True)
class LexicalSimilarityCandidate:
    left_source_id: str
    right_source_id: str
    left_host: str
    right_host: str
    left_content_hash: str
    right_content_hash: str
    shared_four_shingles: int
    union_four_shingles: int
    jaccard: float
    smaller_set_containment: float
    length_ratio: float
    relation: str
    cross_host: bool
    needs_human_lineage_review: bool = True
    shared_origin_established: bool = False


@dataclass(frozen=True)
class SimilarityComponent:
    source_ids: tuple[str, ...]
    observed_hosts: tuple[str, ...]
    direct_candidate_edges: int
    every_pair_verified_similar: bool = False
    no_independence_claim: bool = True


@dataclass(frozen=True)
class SourceSimilarityAudit:
    mandate_digest: str
    source_snapshot_digest: str
    source_policy_digest: str
    retrieval_digest: str
    considered_source_ids: tuple[str, ...]
    compared_source_ids: tuple[str, ...]
    held_source_ids: tuple[str, ...]
    eligible_pair_count: int
    scored_pair_count: int
    similar_pairs: tuple[LexicalSimilarityCandidate, ...]
    components: tuple[SimilarityComponent, ...]
    cross_host_candidate_count: int
    skipped_short_sources: int
    skipped_oversize_sources: int
    threshold_jaccard: float
    threshold_containment: float
    audit_digest: str
    source_body_exposed: bool = False
    algorithm: str = "unicode_nfkc_four_shingle_review_v1"
    external_lookup_performed: bool = False
    lineage_verified: bool = False
    factual_independence_certified: bool = False
    training_or_publication_granted: bool = False


def _shingles(text: str, *, max_words: int) -> frozenset[tuple[str, ...]]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    words = _WORDS.findall(normalized)
    if len(words) > max_words:
        raise ValueError("selected captured text exceeds similarity word cap")
    return frozenset(
        tuple(words[i:i + 4]) for i in range(max(0, len(words) - 3))
    )


def inspect_selected_source_similarity(
    mandate: CampaignMandate,
    snapshot: dict[str, object],
    policy: SourcePolicyProjection,
    retrieval: RetrievalFusion,
    *,
    now: float,
    authorized: bool,
    max_sources: int = 32,
    max_pairs: int = 496,
    max_chars_per_source: int = 24_000,
    max_words_per_source: int = 6_000,
    min_shingles: int = 8,
    jaccard_threshold: float = .78,
    containment_threshold: float = .92,
    min_length_ratio_for_containment: float = .55,
) -> SourceSimilarityAudit:
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    integer(max_sources, "similarity selected-source cap", 1, 32)
    integer(max_pairs, "similarity pair cap", 1, 496)
    integer(max_chars_per_source, "similarity character cap", 128, 24_000)
    integer(max_words_per_source, "similarity word cap", 16, 6_000)
    integer(min_shingles, "similarity minimum shingles", 4, 32)
    for value, name, low, high in (
        (jaccard_threshold, "Jaccard threshold", .5, 1),
        (containment_threshold, "containment threshold", .5, 1),
        (min_length_ratio_for_containment, "containment length ratio", .2, 1),
    ):
        if type(value) not in (float, int) or not isfinite(value) or (
            not low <= value <= high
        ):
            raise ValueError(name + " requires a bounded finite value")
    if not isinstance(policy, SourcePolicyProjection) or (
        not isinstance(retrieval, RetrievalFusion)
    ):
        raise TypeError("typed current policy and retrieval receipts required")
    run = CrawlRun.from_snapshot(snapshot).snapshot()
    revision = run["snapshot_digest"]
    if any(x != mandate.fingerprint for x in (
        policy.mandate_digest, retrieval.mandate_digest
    )):
        raise PermissionError("cross-mandate similarity inspection denied")
    if any(x != revision for x in (
        policy.source_snapshot_digest, retrieval.source_snapshot_digest
    )):
        raise PermissionError("stale similarity source or policy")
    if policy.training_authorized or policy.publication_authorized or (
        retrieval.publication_authorized
    ):
        raise PermissionError("similarity may not grant source publishing rights")
    allowed = set(policy.allowed_source_ids)
    excluded = set(policy.excluded_source_ids)
    if allowed & excluded or allowed | excluded != set(run["sources"]):
        raise PermissionError("incomplete similarity source-use policy")
    if retrieval.excluded_sources != tuple(sorted(excluded)):
        raise PermissionError("source withdrawal set changed since retrieval")
    considered = tuple(sorted({x.source_id for x in retrieval.results}))
    if len(considered) > max_sources:
        raise ValueError("similarity selected source count exceeds cap")
    for row in retrieval.results:
        if row.source_id not in allowed:
            raise PermissionError("unauthorized selected source")
        source = run["sources"][row.source_id]
        if (source["content_hash"] != row.source_hash or
                source["canonical_url"] != row.canonical_url or
                row.host != urlsplit(source["canonical_url"]).hostname or
                row.host not in mandate.scope.allowed_hosts or
                type(row.start) is not int or type(row.end) is not int or
                row.start < 0 or row.end <= row.start or
                row.end > len(source["text"])):
            raise PermissionError("selected similarity source identity mismatch")
        text = source["text"][row.start:row.end]
        if text != row.text or (
            sha256(text.encode("utf-8")).hexdigest() != row.passage_hash
        ):
            raise PermissionError("selected similarity passage changed")
        if not row.matched_objective_ids:
            raise PermissionError("unbound similarity source objective")
    compared: dict[str, tuple[frozenset[tuple[str, ...]], str, str]] = {}
    held = []
    short = 0
    oversize = 0
    for source_id in considered:
        source = run["sources"][source_id]
        raw = source["text"]
        if len(raw) > max_chars_per_source:
            held.append(source_id)
            oversize += 1
            continue
        try:
            shingles = _shingles(raw, max_words=max_words_per_source)
        except ValueError:
            held.append(source_id)
            oversize += 1
            continue
        if len(shingles) < min_shingles:
            held.append(source_id)
            short += 1
            continue
        host = urlsplit(source["canonical_url"]).hostname
        if host is None:
            raise PermissionError("source lacks validated canonical host")
        compared[source_id] = shingles, host, source["content_hash"]
    compared_ids = tuple(sorted(compared))
    pairs_possible = len(compared_ids) * (len(compared_ids) - 1) // 2
    if pairs_possible > max_pairs:
        raise ValueError("similarity pair cap exceeded")
    pairs = []
    for left_id, right_id in combinations(compared_ids, 2):
        left, left_host, left_hash = compared[left_id]
        right, right_host, right_hash = compared[right_id]
        shared = len(left & right)
        if not shared:
            continue
        union = len(left | right)
        jaccard = shared / union
        containment = shared / min(len(left), len(right))
        ratio = min(len(left), len(right)) / max(len(left), len(right))
        same_text = left_hash == right_hash
        similar = same_text or (
            jaccard >= jaccard_threshold or
            (containment >= containment_threshold and
             ratio >= min_length_ratio_for_containment)
        )
        if not similar:
            continue
        pairs.append(LexicalSimilarityCandidate(
            left_source_id=left_id,
            right_source_id=right_id,
            left_host=left_host,
            right_host=right_host,
            left_content_hash=left_hash,
            right_content_hash=right_hash,
            shared_four_shingles=shared,
            union_four_shingles=union,
            jaccard=round(jaccard, 8),
            smaller_set_containment=round(containment, 8),
            length_ratio=round(ratio, 8),
            relation="exact_content" if same_text else "near_duplicate_review",
            cross_host=left_host != right_host,
        ))
    # Transitive clusters are convenient review groupings, not a claim that
    # two unconnected endpoints have any verified direct relation.
    parent = {x: x for x in compared_ids}
    def root(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for pair in pairs:
        a, b = root(pair.left_source_id), root(pair.right_source_id)
        if a != b:
            parent[max(a, b)] = min(a, b)
    groups: dict[str, list[str]] = defaultdict(list)
    for source_id in compared_ids:
        groups[root(source_id)].append(source_id)
    components = []
    for members in groups.values():
        if len(members) < 2:
            continue
        ids = tuple(sorted(members))
        edges = sum(x.left_source_id in ids and x.right_source_id in ids
                    for x in pairs)
        components.append(SimilarityComponent(
            source_ids=ids,
            observed_hosts=tuple(sorted({compared[x][1] for x in ids})),
            direct_candidate_edges=edges,
            every_pair_verified_similar=False,
        ))
    components.sort(key=lambda x: x.source_ids)
    payload = {
        "mandate": mandate.fingerprint,
        "snapshot": revision,
        "policy": policy.policy_digest,
        "retrieval": retrieval.fusion_digest,
        "considered": considered, "compared": compared_ids,
        "held": tuple(held), "short": short, "oversize": oversize,
        "eligible_pairs": pairs_possible,
        "candidates": [asdict(x) for x in pairs],
        "components": [asdict(x) for x in components],
        "thresholds": (jaccard_threshold, containment_threshold,
                       min_length_ratio_for_containment),
        "limits": (max_sources, max_pairs, max_chars_per_source,
                   max_words_per_source, min_shingles),
    }
    return SourceSimilarityAudit(
        mandate_digest=mandate.fingerprint,
        source_snapshot_digest=revision,
        source_policy_digest=policy.policy_digest,
        retrieval_digest=retrieval.fusion_digest,
        considered_source_ids=considered,
        compared_source_ids=compared_ids,
        held_source_ids=tuple(held),
        eligible_pair_count=pairs_possible,
        scored_pair_count=len(pairs),
        similar_pairs=tuple(pairs),
        components=tuple(components),
        cross_host_candidate_count=sum(x.cross_host for x in pairs),
        skipped_short_sources=short,
        skipped_oversize_sources=oversize,
        threshold_jaccard=jaccard_threshold,
        threshold_containment=containment_threshold,
        audit_digest=digest(payload),
    )
