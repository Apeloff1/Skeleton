"""Canonical CrawlRun inspection adapter for Dragon campaign planning.

This does not create, start, resume or advance a crawler; no HTTP is performed.
The canonical run validates full persisted snapshot state and code binding
before any derived recommendations are made. Backend remains responsible for
lease fencing, tenant authorization, consent, and durable Mongo commits.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlsplit
import json

from ..operations import CrawlRun
from .budget import BudgetProjection, project_budget
from .contracts import (
    CampaignMandate, CampaignPlan, ResearchCandidate,
    digest, ensure_snapshot_scope, validate_public_url,
)
from .diagnostics import CampaignDiagnostics, measure_campaign_diagnostics
from .evidence import EvidenceInspection, inspect_campaign_evidence
from .journal import CampaignJournal
from .lineage import (
    DuplicateFamily, LineageImpact, SourceLink,
    exact_duplicate_families, invalidation_closure,
)
from .planner import build_campaign_plan


@dataclass(frozen=True)
class CampaignInspection:
    run_id: str
    run_sequence: int
    snapshot_digest: str
    mandate_digest: str
    budget: BudgetProjection
    plan: CampaignPlan
    evidence: EvidenceInspection
    duplicates: tuple[DuplicateFamily, ...]
    lineage: LineageImpact
    diagnostics: CampaignDiagnostics
    journal_head: str
    inspection_digest: str
    source_authority: str = "canonical_mongo_crawl_snapshot"
    network_executed: bool = False
    knowledge_promoted: bool = False


def frontier_hints(
    snapshot: dict[str, object],
    mandate: CampaignMandate,
    *, max_candidates: int = 512,
) -> tuple[ResearchCandidate, ...]:
    """Construct transparent heuristic ranking hints from existing queued URLs.

    These scores represent neither measured quality nor permission to fetch.
    A future transport step must re-run all canonical admission controls.
    """
    rows = snapshot.get("frontier")
    if not isinstance(rows, list) or len(rows) > max_candidates:
        raise ValueError("frontier capacity exceeded")
    query_terms = set(mandate.query.casefold().split())
    seen = set()
    hints = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid frontier entry")
        url = validate_public_url(row.get("url"), mandate)
        if url in seen:
            raise ValueError("duplicate canonical frontier URL")
        seen.add(url)
        depth = row.get("depth")
        attempts = row.get("attempts")
        if type(depth) is not int or not 0 <= depth <= mandate.request.max_depth:
            raise ValueError("invalid frontier depth")
        if type(attempts) is not int or not 0 <= attempts <= 3:
            raise ValueError("invalid retry count")
        parent = row.get("parent_url")
        if parent is not None:
            validate_public_url(parent, mandate)
        tokens = set(urlsplit(url).path.casefold().replace("/", " ").replace("-", " ").split())
        overlap = len(query_terms.intersection(tokens)) / max(1, len(query_terms))
        # Arbitrary site/path hints cannot create high confidence evidence.
        relevance = min(0.4, 0.1 + 0.3 * overlap)
        information_gain = round(0.15 / (depth + 1), 6)
        quality = 0.1  # Unknown until captured, never a trust promotion.
        hints.append(ResearchCandidate(
            url=url, relevance=round(relevance, 6),
            information_gain=information_gain, quality=quality,
            expected_bytes=mandate.request.max_response_bytes,
            reason="unverified_canonical_frontier_hint",
            parent_url=parent, depth=depth,
        ))
    return tuple(hints)


def inspect_crawl_campaign(
    snapshot: dict[str, object],
    mandate: CampaignMandate,
    *, now: float, authorized: bool,
    candidates: Iterable[ResearchCandidate] | None = None,
    links: Iterable[SourceLink] = (),
    revoked_source_ids: Iterable[str] = (),
    journal: CampaignJournal | None = None,
) -> CampaignInspection:
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    # from_snapshot replays every full canonical invariant, including the code
    # binding, usage counters, frontier, provenance and full snapshot digest.
    run = CrawlRun.from_snapshot(snapshot)
    validated = run.snapshot()
    status = run.status()
    if validated["snapshot_digest"] != snapshot.get("snapshot_digest"):
        raise ValueError("canonical snapshot rebinding")
    encoded = json.dumps(validated, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    projection = project_budget(validated, mandate, snapshot_bytes=len(encoded))
    available = frontier_hints(
        validated, mandate, max_candidates=mandate.limits.max_candidates,
    )
    available_urls = {x.url for x in available}
    if candidates is None:
        proposed = available
    else:
        proposed = tuple(candidates)
        for row in proposed:
            if not isinstance(row, ResearchCandidate):
                raise TypeError("candidate hint must be typed")
            if row.url not in available_urls:
                raise PermissionError("cannot inject URL outside committed frontier")
    plan = build_campaign_plan(
        mandate, proposed, projection, now=now,
        host_ready_at=validated["host_ready"],
        authorized=authorized,
    )
    revoked = tuple(revoked_source_ids)
    if len(revoked) != len(set(revoked)):
        raise ValueError("duplicate source withdrawal identity")
    source_universe = tuple(validated["sources"])
    if any(source_id not in validated["sources"] for source_id in revoked):
        raise ValueError("withdrawal not bound to retained source")
    evidence = inspect_campaign_evidence(
        mandate, run.sources(), now=now, authorized=authorized,
        revoked_source_ids=revoked,
    )
    duplicate_families = exact_duplicate_families(
        ((x.source_id, x.full_content_hash) for x in evidence.sources),
    )
    lineage = invalidation_closure(
        source_universe, links, revoked=revoked, limits=mandate.limits,
    )
    extra_holds = (
        ("revoked_sources_require_revalidation",)
        if lineage.revoked_source_ids else ()
    )
    diagnostics = measure_campaign_diagnostics(
        mandate, projection, evidence, extra_holds=extra_holds,
    )
    record = journal or CampaignJournal(mandate.fingerprint)
    record.verify(mandate)
    payload = {
        "run_id": status["run_id"], "sequence": status["sequence"],
        "snapshot": validated["snapshot_digest"],
        "mandate": mandate.fingerprint,
        "plan": plan.plan_digest,
        "evidence": evidence.evidence_digest,
        "lineage": lineage.lineage_digest,
        "diagnostics": diagnostics.diagnostic_digest,
        "journal": record.head,
    }
    return CampaignInspection(
        run_id=status["run_id"], run_sequence=status["sequence"],
        snapshot_digest=validated["snapshot_digest"],
        mandate_digest=mandate.fingerprint, budget=projection,
        plan=plan, evidence=evidence, duplicates=duplicate_families,
        lineage=lineage, diagnostics=diagnostics,
        journal_head=record.head,
        inspection_digest=digest(payload),
    )
