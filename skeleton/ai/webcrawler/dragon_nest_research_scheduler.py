"""Three lightweight Dragon specialists: deterministic idle-only research queue.

This plans *acquisition requests*, not crawls or credited knowledge. Runtime
workers still require canonical SSRF/robots/rights rules, explicit media
permissions, independently reviewed evidence, global resource grants and
DragonNestReviewBridge approval before a hatchling can advance.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from urllib.parse import urlsplit

from .dragon_nest_progression import (
    DragonNest, LANES, MIN_IDLE_SECONDS, _id, _instant, _tags,
    verify_change_history,
)
from .dragon_resource_session import HardwareSample, plan_resources
from skeleton.ai.game_builder.dragon_source_catalog import canonical_source_url

VIDEO_HOSTS = frozenset({
    "youtube.com", "www.youtube.com", "youtu.be",
    "vimeo.com", "www.vimeo.com",
})


@dataclass(frozen=True)
class ResearchLead:
    """An untrusted discovery hint, not permission to fetch or award XP."""
    source_id: str
    url: str
    tags: tuple[str, ...]
    lane: str
    discovered_at: str
    # An optional *hint* about a source revision, never a verification receipt.
    revision_hint: str = ""
    published_at: str | None = None

    def __post_init__(self) -> None:
        _id(self.source_id)
        _tags(self.tags)
        if self.lane not in LANES:
            raise ValueError("unknown research specialist")
        if (not isinstance(self.url, str) or len(self.url) > 2048
                or any(ord(c) <= 32 or ord(c) == 127 for c in self.url)):
            raise ValueError("bounded absolute public HTTPS URL required")
        p = urlsplit(self.url)
        if (p.scheme != "https" or p.username is not None or p.password is not None
                or p.fragment or p.port not in (None, 443) or not p.hostname):
            raise ValueError("absolute uncredentialed public HTTPS URL required")
        # Full source URL identity passes the existing canonical public-host
        # filter; runtime DNS, redirect, robots and rights checks remain separate.
        if canonical_source_url(self.url) != self.url:
            raise ValueError("canonical public research source required")
        host = p.hostname.lower()
        if (host == "localhost" or host.endswith((".localhost", ".local", ".internal"))
                or "." not in host or not host.isascii()):
            raise ValueError("research leads require public DNS names")
        if (self.lane == "video") != (host in VIDEO_HOSTS):
            if self.lane != "updates" or host in VIDEO_HOSTS:
                raise ValueError("research specialist/media mismatch")
        _instant(self.discovered_at)
        if self.published_at is not None:
            published = _instant(self.published_at)
            if published > _instant(self.discovered_at):
                raise ValueError("publication hint follows discovery")
        if (not isinstance(self.revision_hint, str) or len(self.revision_hint) > 128
                or any(ord(ch) < 32 for ch in self.revision_hint)):
            raise ValueError("revision hint is not bounded")


@dataclass(frozen=True)
class ResearchAssignment:
    lane: str
    source_id: str
    url: str
    importance: str
    priority: int
    evidence_only: bool = True
    # Never allow a planner to self-authorize execution or promotion.
    execution_authorized: bool = False
    memory_promotion_authorized: bool = False


@dataclass(frozen=True)
class IdleResearchPlan:
    owner: str
    at: str
    assignments: tuple[ResearchAssignment, ...]
    reason: str
    total_leads: int
    suppressed_duplicates: int
    requires_worker_admission: bool = True
    execution_authorized: bool = False
    memory_promotion_authorized: bool = False


@dataclass(frozen=True)
class IdleResearchPolicy:
    min_idle_seconds: int = MIN_IDLE_SECONDS
    max_leads: int = 512
    max_per_lane: int = 2
    max_assignments: int = 6

    def __post_init__(self) -> None:
        if (type(self.min_idle_seconds) is not int
                or not 300 <= self.min_idle_seconds <= 86400
                or type(self.max_leads) is not int or not 1 <= self.max_leads <= 2048
                or type(self.max_per_lane) is not int or not 1 <= self.max_per_lane <= 8
                or type(self.max_assignments) is not int
                or not 1 <= self.max_assignments <= 24):
            raise ValueError("invalid bounded idle research policy")


def plan_idle_research(
    nest: DragonNest, leads: tuple[ResearchLead, ...],
    sample: HardwareSample, *, at: str, idle_since: str,
    now_seconds: float, consented: bool, authorized: bool,
    policy: IdleResearchPolicy = IdleResearchPolicy(),
) -> IdleResearchPlan:
    """Three-lane, deterministic fairness and relevance admission planning.

    Verified canonical knowledge is never inferred from URLs or hint digests.
    A worker must re-check resource allocation after every suspension, and
    a new foreground activity must cancel this plan before any dispatch.
    """
    if (not isinstance(nest, DragonNest) or not verify_change_history(nest)
            or not isinstance(policy, IdleResearchPolicy)):
        raise ValueError("authenticated and untampered nest required")
    _id(nest.owner)
    now, since = _instant(at), _instant(idle_since)
    if (type(now_seconds) not in (int, float) or not math.isfinite(now_seconds)
            or now_seconds < 0 or not isinstance(leads, tuple)
            or len(leads) > policy.max_leads
            or any(not isinstance(item, ResearchLead) for item in leads)):
        raise ValueError("bounded typed research lead batch and clock required")
    def empty(reason: str, duplicates: int = 0) -> IdleResearchPlan:
        return IdleResearchPlan(
            nest.owner, now.isoformat().replace("+00:00", "Z"),
            (), reason, len(leads), duplicates,
        )
    if authorized is not True or consented is not True:
        return empty("authorization_or_consent_absent")
    if len(nest.children) != 3 or nest.stage != "adult":
        return empty("three_hatchlings_not_unlocked")
    if since > now or (now - since).total_seconds() < policy.min_idle_seconds:
        return empty("foreground_or_insufficient_idle_time")
    resource_plan = plan_resources(sample, now=now_seconds, foreground=False)
    if not resource_plan.background_allowed:
        return empty(resource_plan.reason)
    # The source ID/content pair can be reobserved without earning XP. Only
    # prospective unseen identities/versions have a reason to be rechecked.
    by_lane = {
        child.lane: {(sid, digest) for sid, digest, _ in child.evidence}
        for child in nest.children
    }
    candidates: dict[str, list[tuple[int, str, ResearchLead, str]]] = {
        lane: [] for lane in LANES
    }
    duplicates = 0
    seen = set()
    for lead in leads:
        identity = (lead.lane, lead.source_id, lead.revision_hint)
        if identity in seen:
            duplicates += 1
            continue
        seen.add(identity)
        observed = _instant(lead.discovered_at)
        if observed > now or (now - observed).total_seconds() > 90 * 86400:
            continue
        published = _instant(lead.published_at) if lead.published_at is not None else None
        if (lead.lane == "updates" and
                (published is None or (now - published).total_seconds() > 180 * 86400)):
            continue
        tags = set(_tags(lead.tags))
        if not tags:
            continue
        on_task = tags.intersection(nest.focus_tags)
        adjacent = tags.intersection(nest.adjacent_tags)
        if not on_task and not adjacent:
            continue
        # The revision is only a hint, never sufficient evidence for growth.
        if lead.revision_hint and (
            lead.source_id, lead.revision_hint
        ) in by_lane[lead.lane]:
            duplicates += 1
            continue
        rank = 120 if on_task else 60
        rank += min(20, 5 * len(on_task)) + min(10, 2 * len(adjacent))
        rank += max(0, 15 - int((now - observed).total_seconds() // 86400))
        if lead.lane == "updates":
            rank += max(0, 15 - int((now - published).total_seconds() // 86400))
        reason = "task" if on_task else "adjacent"
        candidates[lead.lane].append((
            rank, lead.source_id, lead, reason,
        ))
    for lane in LANES:
        candidates[lane].sort(key=lambda x: (-x[0], x[1], x[2].url))
    assignments = []
    per_lane = {lane: 0 for lane in LANES}
    # Round-robin across the specialist trio prevents an article backlog from
    # starving video or update research. Each lane also has a strict budget.
    max_total = min(policy.max_assignments, resource_plan.retrieval_candidates)
    for _ in range(max_total):
        chosen_lane = next(
            (lane for lane in LANES
             if per_lane[lane] < policy.max_per_lane and candidates[lane]), None
        )
        if chosen_lane is None:
            break
        # Across cycles, favor the lane with the fewest issued jobs, then the
        # largest task relevance. Tie-break remains stable on specialist order.
        viable = [
            (per_lane[lane], -candidates[lane][0][0], LANES.index(lane), lane)
            for lane in LANES
            if per_lane[lane] < policy.max_per_lane and candidates[lane]
        ]
        _, _, _, lane = min(viable)
        priority, _, lead, importance = candidates[lane].pop(0)
        assignments.append(ResearchAssignment(
            lane, lead.source_id, lead.url, importance, priority,
        ))
        per_lane[lane] += 1
    return IdleResearchPlan(
        nest.owner, now.isoformat().replace("+00:00", "Z"),
        tuple(assignments),
        "untrusted_intents_require_separate_worker_admission",
        len(leads), duplicates,
    )
