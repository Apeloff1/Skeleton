"""Deterministic cross-subsystem Dragon research portfolio proposal.

Turns several user-defined game-engine/editor knowledge goals into a shared,
bounded set of source *discovery* suggestions. A single URL can help multiple
facets; suggestions are never proof, custody, permission, license clearance,
crawler execution, model training or memory promotion.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from .dragon_discovery_mission import MissionSourceScout, SourceMission, _tokens
from .dragon_almanacs import DragonAlmanacs, _auth
from .reviewed_knowledge import _integer

_AXIS = re.compile(r"[a-z][a-z0-9_]{1,39}\Z")
_MAX_AXES = 24


@dataclass(frozen=True, slots=True)
class PortfolioAxis:
    axis_id: str
    question: str
    minimum: int = 2
    importance: int = 5

    def __post_init__(self) -> None:
        if not isinstance(self.axis_id,str) or not _AXIS.fullmatch(self.axis_id):
            raise ValueError("invalid portfolio axis identifier")
        if (not isinstance(self.question,str) or
                not 3 <= len(self.question) <= 200 or
                self.question != self.question.strip() or
                any(ord(ch) < 32 or ord(ch) == 127 for ch in self.question)):
            raise ValueError("invalid portfolio research question")
        _integer(self.minimum, "axis required leads", 1, 10)
        _integer(self.importance, "axis importance", 1, 10)


@dataclass(frozen=True, slots=True)
class PortfolioRequest:
    mission: SourceMission
    axes: tuple[PortfolioAxis, ...]
    total_limit: int = 30
    per_axis_candidates: int = 15
    max_per_host: int = 3
    indexed: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.mission,SourceMission):
            raise ValueError("typed root mission required")
        if (not isinstance(self.axes,tuple) or
                not 1 <= len(self.axes) <= _MAX_AXES or
                any(not isinstance(x,PortfolioAxis) for x in self.axes) or
                len({x.axis_id for x in self.axes}) != len(self.axes)):
            raise ValueError("bounded unique portfolio axes required")
        _integer(self.total_limit, "portfolio source cap", 1, 100)
        _integer(self.per_axis_candidates, "per axis candidates", 1, 100)
        _integer(self.max_per_host, "max leads per host", 1, 20)
        if type(self.indexed) is not bool:
            raise ValueError("indexed selection flag must be boolean")


class MissionPortfolio:
    """Owner-fenced greedy multi-axis planning over the existing mission scout."""

    def __init__(self, almanacs: DragonAlmanacs):
        if not isinstance(almanacs,DragonAlmanacs):
            raise TypeError("canonical almanac owner required")
        self.scout = MissionSourceScout(almanacs)

    def build(self, owner: str, request: PortfolioRequest, *,
              authorized: bool, topic: str | None = None) -> dict:
        _auth(owner, authorized)
        if not isinstance(request,PortfolioRequest):
            raise ValueError("typed portfolio request required")
        candidate_scores = {}
        observations = {}
        axes = {}
        scan_totals = {}
        indexed_complete = True
        generic = _tokens(request.mission.goal)
        stopwords = frozenset({"and", "the", "with", "for", "from",
                               "some", "into", "about", "that", "this"})
        for axis in request.axes:
            distinct_axis_terms = _tokens(axis.question) - generic - stopwords
            if not distinct_axis_terms:
                raise ValueError("portfolio axis has no distinctive research terms")
            goal = axis.question + " " + request.mission.goal
            # SourceMission already rejects nonfinite/scalar and unbounded
            # inputs; do not bypass its admission path for portfolio missions.
            if len(goal) > 400:
                raise ValueError("combined portfolio question exceeds mission budget")
            mission = SourceMission(
                goal, platform=request.mission.platform,
                genre=request.mission.genre, era=request.mission.era,
                prefer_video=request.mission.prefer_video,
                limit=request.per_axis_candidates,
                scan_budget=request.mission.scan_budget,
            )
            result = self.scout.propose(
                owner, mission, authorized=True,
                topic=topic, indexed=request.indexed)
            axes[axis.axis_id] = axis
            scan_totals[axis.axis_id] = {
                "scanned": result["scanned"],
                "candidate_matches": result["eligible_metadata_matches"],
                "truncated": result["scan_truncated"],
                "missing_goal_terms": result["unmatched_goal_terms_in_scanned_corpus"],
            }
            if (request.indexed and
                    not result["index_health"]["coverage_complete"]):
                indexed_complete = False
            for hit in result["selection"]:
                # Shared generic project terms cannot masquerade as subsystem
                # coverage. Only a source with at least one distinct axis term
                # contributes an actual discovery candidate for that axis.
                if not (distinct_axis_terms &
                        set(hit.get("matched_goal_terms", []))):
                    continue
                sid = hit["source_id"]
                if sid in observations:
                    prior = observations[sid]
                    for field in ("url", "host", "kind", "policy_state",
                                  "needs_manual_rights_review"):
                        if hit[field] != prior[field]:
                            raise ValueError("contradictory source identity across axes")
                else:
                    observations[sid] = hit
                candidate_scores.setdefault(sid, {})[axis.axis_id] = hit["score"]
        # Prefer marginal coverage of unmet important axes. A source that
        # simultaneously addresses two axes can be more useful than two
        # duplicates, but multiple hosts are only diversity, not independence.
        coverage = {axis.axis_id: 0 for axis in request.axes}
        host_counts = {}
        remaining = set(candidate_scores)
        chosen = []
        while remaining and len(chosen) < request.total_limit:
            ranked = []
            for sid in remaining:
                hit = observations[sid]
                if host_counts.get(hit["host"], 0) >= request.max_per_host:
                    continue
                gain = 0
                for axis_id, score in candidate_scores[sid].items():
                    axis = axes[axis_id]
                    deficit = max(0, axis.minimum - coverage[axis_id])
                    if deficit:
                        gain += axis.importance * score * (1 + deficit / axis.minimum)
                if hit["needs_manual_rights_review"]:
                    gain *= 0.8
                if gain > 0:
                    ranked.append((gain, sid))
            if not ranked:
                break
            gain,sid = min(ranked, key=lambda row:(-round(row[0], 9), row[1]))
            remaining.remove(sid)
            hit = observations[sid]
            host_counts[hit["host"]] = host_counts.get(hit["host"], 0) + 1
            for axis_id in candidate_scores[sid]:
                coverage[axis_id] += 1
            chosen.append({
                "source_id": sid, "url": hit["url"], "host": hit["host"],
                "kind": hit["kind"], "marginal_discovery_gain": round(gain, 6),
                "axis_scores": dict(sorted(candidate_scores[sid].items())),
                "needs_manual_rights_review": hit["needs_manual_rights_review"],
                "rights_risk_tokens": hit["rights_risk_tokens"],
                "raw_provenance_receipts": hit["raw_provenance_receipts"],
                "policy_state": hit["policy_state"],
                "source_review_required": True,
                "crawler_authorized": False,
                "training_authorized": False,
            })
            if all(coverage[x.axis_id] >= x.minimum for x in request.axes):
                break
        report = []
        for axis in request.axes:
            count = coverage[axis.axis_id]
            report.append({
                "axis_id": axis.axis_id,
                "question": axis.question,
                "importance": axis.importance,
                "minimum": axis.minimum,
                "proposed_leads": count,
                "missing_leads": max(0, axis.minimum - count),
                "coverage_state": (
                    "candidate_quota_met_not_evidence_approved"
                    if count >= axis.minimum else "discovery_gap"),
                "scout": scan_totals[axis.axis_id],
            })
        return {
            "schema": "skeleton.dragon.discovery_portfolio.v1",
            "owner": owner, "topic": topic,
            "platform": request.mission.platform,
            "genre": request.mission.genre, "era": request.mission.era,
            "indexed_search": request.indexed,
            "indexed_corpus_current": indexed_complete if request.indexed else None,
            "selected": chosen, "axis_coverage": report,
            "uncovered_axes": [x["axis_id"] for x in report if x["missing_leads"]],
            "candidate_pool": len(candidate_scores),
            "host_diversity_is_not_independence": True,
            "portfolio_authority": "unreviewed_discovery_metadata_only",
            "acquisition_queue_modified": False,
            "source_use_authorized": False,
            "memory_promotion_authorized": False,
            "training_authorized": False,
        }
