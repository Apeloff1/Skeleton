"""Bounded source acquisition economics (mission ranks 17–20).

All functions are offline planners: they never fetch, circumvent robots/terms,
schedule an OS background task, spend external quotas, or promote knowledge.
An executor must independently recheck SSRF/robots/host/redirect permissions.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import exp, isfinite, log2
from typing import Iterable
from urllib.parse import urlsplit
import json

from .core import CrawlPolicy, canonicalize_url
from .dragon_provenance_assurance import ProvenanceAssurance


@dataclass(frozen=True)
class AcquisitionCandidate:
    url: str
    relevance: float
    expected_information_gain: float
    source_quality: float
    expected_bytes: int
    last_host_seen: float | None = None


@dataclass(frozen=True)
class PrioritizedAcquisition:
    url: str
    host: str
    expected_bytes: int
    score: float
    information_gain: float
    admitted: bool
    reason: str


@dataclass(frozen=True)
class HostDispatch:
    url: str
    host: str
    ready_at: float
    rank: int
    priority: float


@dataclass(frozen=True)
class RecrawlSource:
    source_id: str
    canonical_url: str
    last_fetched: float
    last_changed: float
    volatility: float
    importance: float
    consecutive_unchanged: int = 0


@dataclass(frozen=True)
class RecrawlDue:
    source_id: str
    next_due: float
    due: bool
    urgency: float
    revisit_interval: float


@dataclass(frozen=True)
class MissionStopDecision:
    should_stop: bool
    review_required: bool
    unmet_goals: tuple[str, ...]
    recommended_next: tuple[str, ...]
    fingerprint: str


def _bound(x: object, name: str) -> float:
    if not isinstance(x, (int,float)) or isinstance(x,bool) or not isfinite(x) or not 0 <= x <= 1:
        raise ValueError(f"invalid {name}")
    return float(x)


def _hash(data: object) -> str:
    return sha256(json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode()).hexdigest()


# 17. Rank new information by predicted value, quality and bounded byte costs.
def _public_host(host: str) -> bool:
    return (
        "." in host
        and not host.rstrip(".").endswith(
            (".local", ".localhost", ".internal", ".test", ".invalid")
        )
    )


def rank_acquisition_candidates(
    candidates: Iterable[AcquisitionCandidate], *,
    policy: CrawlPolicy = CrawlPolicy(),
    max_candidates: int = 10000,
    byte_reference: int = 200000,
) -> tuple[PrioritizedAcquisition, ...]:
    items=tuple(candidates)
    if not 1 <= max_candidates <= 100000 or len(items)>max_candidates:
        raise ValueError("acquisition candidate budget exceeded")
    if not 1 <= byte_reference <= 100000000:
        raise ValueError("invalid byte reference")
    ranked:dict[str,PrioritizedAcquisition]={}
    for entry in items:
        if not isinstance(entry,AcquisitionCandidate):
            raise ValueError("invalid acquisition candidate")
        relevance=_bound(entry.relevance,"query relevance")
        gain=_bound(entry.expected_information_gain,"information gain")
        quality=_bound(entry.source_quality,"source quality")
        if not isinstance(entry.expected_bytes,int) or isinstance(entry.expected_bytes,bool) or entry.expected_bytes < 0:
            raise ValueError("invalid expected bytes")
        if entry.last_host_seen is not None and (
            not isinstance(entry.last_host_seen,(int,float))
            or isinstance(entry.last_host_seen,bool)
            or not isfinite(entry.last_host_seen)
            or entry.last_host_seen<0
        ):
            raise ValueError("invalid host observation")
        try:
            canonical=canonicalize_url(entry.url)
        except (ValueError,UnicodeError):
            raise ValueError("invalid acquisition URL") from None
        host=urlsplit(canonical).hostname or ""
        admitted=policy.admits(canonical) and _public_host(host)
        if not admitted:
            score=0.0
            reason="policy_denied"
        elif entry.expected_bytes>policy.max_response_bytes:
            admitted=False
            score=0.0
            reason="response_size_budget"
        else:
            # Benefit is bounded and cannot be increased by submitting the
            # same URL repeatedly. Cost penalizes expensive low-value fetches.
            reward=.45*gain+.3*relevance+.25*quality
            cost=1+.5*(entry.expected_bytes/byte_reference)
            score=round(reward/cost,8)
            reason="candidate_not_authorized_for_fetch"
        result=PrioritizedAcquisition(canonical,host,entry.expected_bytes,
                                     score,gain,admitted,reason)
        before=ranked.get(canonical)
        if before is None or (result.score,result.information_gain)>(
            before.score,before.information_gain
        ):
            ranked[canonical]=result
    return tuple(sorted(ranked.values(),key=lambda c:(
        not c.admitted,-c.score,c.host,c.url,
    )))


# 18. Fair host-aware allocation; rate/robots checks still required by runner.
def allocate_host_dispatches(
    ranked: Iterable[PrioritizedAcquisition], *,
    now: float, host_ready_at: dict[str,float] | None = None,
    max_dispatch: int = 100, max_per_host: int = 4,
    host_delay: float = 1.0, policy: CrawlPolicy = CrawlPolicy(),
) -> tuple[HostDispatch, ...]:
    if not isinstance(now,(int,float)) or isinstance(now,bool) or not isfinite(now) or now<0:
        raise ValueError("invalid dispatch time")
    if not 1 <= max_dispatch <= 10000 or not 1 <= max_per_host <= 1000:
        raise ValueError("invalid dispatch capacity")
    if not isinstance(host_delay,(int,float)) or isinstance(host_delay,bool) or not isfinite(host_delay) or host_delay<0:
        raise ValueError("invalid host delay")
    times=host_ready_at or {}
    if any(not isinstance(v,(int,float)) or isinstance(v,bool) or not isfinite(v) or v<0
           for v in times.values()):
        raise ValueError("invalid host-ready schedule")
    # Stable round-robin: avoid one prolific host starving all the others.
    hosts:dict[str,list[PrioritizedAcquisition]]={}
    seen=set()
    for entry in ranked:
        if not isinstance(entry,PrioritizedAcquisition):
            raise ValueError("invalid planned acquisition")
        if not entry.admitted or entry.url in seen:
            continue
        seen.add(entry.url)
        try:
            identity=canonicalize_url(entry.url)
        except (ValueError,UnicodeError) as exc:
            raise ValueError("invalid admitted dispatch URL") from exc
        if identity != entry.url or urlsplit(identity).hostname != entry.host:
            raise ValueError("host identity mismatch")
        if not policy.admits(identity) or not _public_host(entry.host):
            raise PermissionError("dispatch candidate violates destination policy")
        if entry.expected_bytes>policy.max_response_bytes:
            raise PermissionError("dispatch candidate exceeds response budget")
        if not isinstance(entry.score,(int,float)) or not isfinite(entry.score) or entry.score < 0:
            raise ValueError("invalid dispatch score")
        hosts.setdefault(entry.host,[]).append(entry)
    for group in hosts.values():
        group.sort(key=lambda x:(-x.score,x.url))
    ordered_hosts=sorted(hosts, key=lambda h:(-hosts[h][0].score,h))
    output=[]
    counts={host:0 for host in ordered_hosts}
    next_ready={host:max(float(now),float(times.get(host,0))) for host in ordered_hosts}
    while len(output)<max_dispatch:
        progressed=False
        for host in ordered_hosts:
            if len(output)>=max_dispatch:
                break
            if not hosts[host] or counts[host]>=max_per_host:
                continue
            item=hosts[host].pop(0)
            counts[host]+=1
            output.append(HostDispatch(
                item.url,host,round(next_ready[host],6),len(output)+1,item.score,
            ))
            next_ready[host]+=host_delay
            progressed=True
        if not progressed:
            break
    return tuple(output)


# 19. Adaptive recrawl frequency from observed volatility and mission value.
def plan_adaptive_recrawls(
    sources: Iterable[RecrawlSource], *,
    now: float, minimum_interval: float = 3600,
    maximum_interval: float = 30*86400,
    max_sources: int = 10000,
) -> tuple[RecrawlDue, ...]:
    values=tuple(sources)
    if not isinstance(now,(int,float)) or isinstance(now,bool) or not isfinite(now) or now<0:
        raise ValueError("invalid recrawl time")
    if any(not isinstance(x,(int,float)) or isinstance(x,bool) or not isfinite(x)
           for x in (minimum_interval,maximum_interval)) or not 1 <= minimum_interval <= maximum_interval:
        raise ValueError("invalid recrawl interval bounds")
    if not 1 <= max_sources <= 100000 or len(values)>max_sources:
        raise ValueError("recrawl source budget exceeded")
    seen=set()
    scheduled=[]
    for source in values:
        if not isinstance(source,RecrawlSource):
            raise ValueError("invalid recrawl source")
        if source.source_id in seen or not source.source_id or len(source.source_id)>256:
            raise ValueError("duplicate/invalid source ID")
        seen.add(source.source_id)
        try:
            canonical=canonicalize_url(source.canonical_url)
        except (ValueError,UnicodeError) as exc:
            raise ValueError("invalid recrawl target") from exc
        if not CrawlPolicy().admits(canonical) or not _public_host(urlsplit(canonical).hostname or ""):
            raise ValueError("recrawl target fails egress policy")
        importance=_bound(source.importance,"recrawl importance")
        volatility=_bound(source.volatility,"recrawl volatility")
        if (not isinstance(source.consecutive_unchanged,int)
                or isinstance(source.consecutive_unchanged,bool)
                or not 0 <= source.consecutive_unchanged <= 100000):
            raise ValueError("invalid stability history")
        for value in (source.last_fetched,source.last_changed):
            if not isinstance(value,(int,float)) or isinstance(value,bool) or not isfinite(value) or not 0<=value<=now:
                raise ValueError("invalid prior fetch/change timestamp")
        if source.last_changed > source.last_fetched:
            raise ValueError("source change cannot postdate last fetch")
        # Importance/volatility shorten the interval; stable results lengthen
        # it, all within hard limits. Never schedule a fetch here.
        volatility_factor=1 + 7*(1-volatility)
        importance_factor=1 + 3*(1-importance)
        stability=min(16,1+source.consecutive_unchanged/2)
        interval=max(float(minimum_interval), min(
            float(maximum_interval),
            float(minimum_interval)*volatility_factor*importance_factor*stability,
        ))
        due=source.last_fetched+interval
        overdue=max(0.,float(now)-due)
        urgency=round(min(1.,overdue/max(1.,interval)),8)
        scheduled.append(RecrawlDue(
            source.source_id,round(due,6),due<=now,urgency,
            round(interval,6),
        ))
    return tuple(sorted(scheduled,key=lambda x:(
        not x.due,-x.urgency,x.next_due,x.source_id,
    )))


# 20. Explicit mission stop gate rather than endless duplicate acquisitions.
def decide_mission_stop(
    assurance: ProvenanceAssurance, *,
    remaining_requests: int, novelty_scores: Iterable[float],
    minimum_groups: int = 2, novelty_floor: float = .03,
    plateau_window: int = 5, max_scores: int = 10000,
) -> MissionStopDecision:
    if not isinstance(assurance,ProvenanceAssurance):
        raise ValueError("provenance assurance required")
    if not isinstance(remaining_requests,int) or isinstance(remaining_requests,bool) or remaining_requests<0:
        raise ValueError("invalid remaining request count")
    if not 2 <= minimum_groups <= 1000 or not 1<=plateau_window<=1000 or not 1<=max_scores<=100000:
        raise ValueError("invalid stopping policy")
    floor=_bound(novelty_floor,"novelty floor")
    history=tuple(novelty_scores)
    if len(history)>max_scores:
        raise ValueError("novelty history budget exceeded")
    scores=tuple(_bound(x,"novelty observation") for x in history)
    adequate=(assurance.independent_groups>=minimum_groups and
              assurance.candidate_for_review and not assurance.belief.conflicting)
    plateau=(len(scores)>=plateau_window and
             max(scores[-plateau_window:])<=floor)
    reasons=[]
    if assurance.independent_groups<minimum_groups:
        reasons.append("independent_corroboration")
    if assurance.belief.conflicting:
        reasons.append("contradiction_review")
    if not assurance.source_coverage_complete:
        reasons.append("reread_coverage")
    if not assurance.candidate_for_review and not reasons:
        reasons.append("assurance_threshold")
    if not adequate and remaining_requests==0:
        reasons.append("budget_exhausted_with_unresolved_goals")
    if not adequate and remaining_requests>0 and plateau:
        reasons.append("novelty_plateau_unresolved")
    # A budget failure is a stop for additional *fetches*, not approval to
    # publish the claim. Good evidence is routed to human review; continued
    # uncertainty requires more independent research if budgets permit.
    stop = adequate or remaining_requests==0 or plateau
    actions = (
        ("submit_for_human_review",) if adequate else
        ("increase_authorized_budget_or_escalate",) if remaining_requests==0 else
        ("escalate_research_strategy",) if plateau else
        ("seek_new_independent_sources",) if assurance.independent_groups<minimum_groups else
        ("target_contradictions",) if assurance.belief.conflicting else
        ("schedule_reread_and_calibration",)
    )
    digest=_hash({
        "schema":"skeleton.crawler.mission_stop.v1",
        "assurance":assurance.fingerprint,
        "budget":remaining_requests,
        "novelty":scores,
        "minimum_groups":minimum_groups,
        "floor":floor,"window":plateau_window,
        "stop":stop,"reasons":reasons,"next":actions,
    })
    return MissionStopDecision(
        stop,True,tuple(reasons),actions,digest,
    )
