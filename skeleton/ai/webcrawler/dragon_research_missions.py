"""Deterministic research mission planning for consented dragon interests.

Plans encyclopedia, scholarly and geographic discovery without making
network requests. Publisher licensing and human review remain required
before any content is archived or promoted into knowledge.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite
from .dragon_research_discovery import DiscoveryQuery, ResearchSource


@dataclass(frozen=True)
class ResearchInterest:
    topic: str
    weight: float
    sensitive: bool = False


@dataclass(frozen=True)
class MissionPolicy:
    max_interests: int = 20
    max_queries: int = 100
    include_places: bool = False


@dataclass(frozen=True)
class ResearchMission:
    owner: str
    queries: tuple[DiscoveryQuery, ...]
    fingerprint: str


def plan_research(owner: str, interests: tuple[ResearchInterest, ...], *,
                  authorized: bool, geographic_consent: bool = False,
                  policy: MissionPolicy = MissionPolicy()) -> ResearchMission:
    if not authorized:
        raise PermissionError("research planning requires consent")
    if not isinstance(owner, str) or not 1 <= len(owner) <= 128:
        raise ValueError("invalid owner")
    if not 1 <= policy.max_interests <= 1000 or not 1 <= policy.max_queries <= 1000:
        raise ValueError("invalid research budgets")
    if not 1 <= len(interests) <= policy.max_interests:
        raise ValueError("interest budget exceeded")
    sources = [
        ResearchSource.WIKIPEDIA,
        ResearchSource.CROSSREF,
        ResearchSource.OPENALEX,
        ResearchSource.EUROPE_PMC,
    ]
    if policy.include_places and geographic_consent:
        sources.append(ResearchSource.OPENSTREETMAP)
    topics = {}
    for interest in interests:
        if interest.sensitive:
            continue
        if not isinstance(interest.topic, str):
            raise ValueError("invalid topic")
        topic = " ".join(interest.topic.casefold().split())
        if not 2 <= len(topic) <= 240 or not isfinite(interest.weight):
            raise ValueError("invalid research interest")
        if not 0 < interest.weight <= 1:
            raise ValueError("invalid interest weight")
        topics[topic] = max(topics.get(topic, 0), interest.weight)
    if not topics:
        raise ValueError("no eligible research interests")
    ordered = sorted(topics.items(), key=lambda item: (-item[1], item[0]))
    queries = []
    for topic, _ in ordered:
        for source in sources:
            if len(queries) >= policy.max_queries:
                break
            queries.append(DiscoveryQuery(
                topic, sources=(source,), limit_per_source=10,
            ))
    payload = json.dumps(
        [owner, [(query.terms, query.sources[0].value) for query in queries]],
        separators=(",", ":"), ensure_ascii=True,
    )
    return ResearchMission(
        owner, tuple(queries), sha256(payload.encode()).hexdigest(),
    )
