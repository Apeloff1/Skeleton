"""Deterministic evidence-led skill tree for the Dragon research companion.

No independent event journal or mutable inventory exists. Unlocks are derived
from a single canonical revision; they are not authorization, verified facts,
training examples or a reward for hitting a site more often. The journal
carries no source text, URL, query term, or transferable financial value.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re

SCHEMA = "skeleton.dragon.questbook.v1"
_HEX = re.compile(r"[a-f0-9]{64}\Z")
MAX_CONTRIBUTIONS = 64
MAX_QUESTS = 12


@dataclass(frozen=True)
class Contribution:
    source_id: str
    sequence: int
    host: str
    habitat: str
    reward: float
    novelty: float
    relevance: float
    coverage_added: int
    multi_origin_added: int
    accepted: bool


@dataclass(frozen=True)
class Quest:
    code: str
    branch: str
    target: int
    prerequisite: str | None = None


QUESTS = (
    Quest("first_scale", "discovery", 1),
    Quest("novel_trail", "discovery", 3, "first_scale"),
    Quest("cartographer", "discovery", 8, "novel_trail"),
    Quest("first_insight", "scholar", 1),
    Quest("mosaic", "scholar", 70, "first_insight"),
    Quest("many_perspectives", "scholar", 2, "mosaic"),
    Quest("new_habitat", "ecology", 2),
    Quest("habitat_keeper", "ecology", 3, "new_habitat"),
    Quest("far_roamer", "ecology", 3, "new_habitat"),
    Quest("measured_expedition", "stewardship", 4),
    Quest("careful_researcher", "stewardship", 60, "measured_expedition"),
    Quest("balanced_mastery", "stewardship", 4, "careful_researcher"),
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def _validate(rows: list[Contribution]) -> None:
    if not isinstance(rows, list) or len(rows) > MAX_CONTRIBUTIONS:
        raise ValueError("companion contribution capacity exceeded")
    sequence = 0
    ids = set()
    for row in rows:
        if (not isinstance(row, Contribution) or not isinstance(row.source_id, str)
                or not _HEX.fullmatch(row.source_id) or row.source_id in ids
                or type(row.sequence) is not int or not sequence < row.sequence <= 10000
                or not isinstance(row.host, str) or not 1 <= len(row.host) <= 253
                or row.habitat not in {"web", "document", "structured", "media", "text", "artifact"}
                or type(row.accepted) is not bool):
            raise ValueError("companion contribution identity mismatch")
        for value in (row.reward, row.novelty, row.relevance):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("companion contribution score exceeds bounds")
        if (type(row.coverage_added) is not int or not 0 <= row.coverage_added <= 32
                or type(row.multi_origin_added) is not int or not 0 <= row.multi_origin_added <= 32
                or (not row.accepted and (row.reward or row.coverage_added or row.multi_origin_added))):
            raise ValueError("uncredited evidence cannot unlock quests")
        sequence = row.sequence
        ids.add(row.source_id)


def derive_questbook(rows: list[Contribution], *, term_count: int,
                     settled: int, request_budget: int, source_budget: int) -> dict:
    """Progress is reversible, not a second store or a permanent trophy ledger."""
    _validate(rows)
    if (type(term_count) is not int or not 0 <= term_count <= 32
            or type(settled) is not int or not 0 <= settled <= 128
            or type(request_budget) is not int or not 1 <= request_budget <= 128
            or type(source_budget) is not int or not 1 <= source_budget <= 64
            or settled > request_budget or len(rows) > source_budget):
        raise ValueError("invalid questbook scope")
    useful = [row for row in rows if row.accepted and row.reward >= .05]
    # Links are exact *source identities*, never raw snippets or new URLs.
    first = useful[:1]
    insight = [row for row in useful if row.coverage_added]
    multi = [row for row in useful if row.multi_origin_added]
    media = {}
    origins = {}
    for row in useful:
        media.setdefault(row.habitat, row)
        origins.setdefault(row.host, row)
    media_rows = list(media.values())
    origin_rows = list(origins.values())
    terms_covered = min(term_count, sum(row.coverage_added for row in insight))
    multi_count = min(term_count, sum(row.multi_origin_added for row in multi))
    coverage_pct = int(100 * terms_covered / term_count) if term_count else 0
    # No bonus for denials, interruptions or repeated recovery. Acquisition
    # efficiency is a descriptive objective with a minimum sample size.
    efficiency = int(100 * len(useful) / max(1, settled))
    mastery_count = sum((len(useful) >= 3, coverage_pct >= 70,
                         len(origins) >= 2, len(media) >= 2))
    metric = {
        "first_scale": (len(first), first, True),
        "novel_trail": (len(useful), useful[:3], source_budget >= 3),
        "cartographer": (len(useful), useful[:8], source_budget >= 8),
        "first_insight": (len(insight), insight[:1], term_count > 0),
        "mosaic": (coverage_pct, insight, term_count > 0),
        "many_perspectives": (multi_count, multi, term_count >= 2),
        "new_habitat": (len(media), media_rows[:2], source_budget >= 2),
        "habitat_keeper": (len(media), media_rows[:3], source_budget >= 3),
        "far_roamer": (len(origins), origin_rows[:3], source_budget >= 3),
        "measured_expedition": (len(useful), useful[:4], source_budget >= 4 and request_budget >= 4),
        "careful_researcher": (efficiency, useful[:8], settled >= 4),
        "balanced_mastery": (mastery_count, useful, source_budget >= 3 and term_count > 0),
    }
    unlocked = set()
    quests = []
    for quest in QUESTS:
        current, evidence, applicable = metric[quest.code]
        available = applicable and (quest.prerequisite is None or quest.prerequisite in unlocked)
        complete = available and current >= quest.target and bool(evidence)
        if complete:
            unlocked.add(quest.code)
        state = "completed" if complete else "active" if available else "locked"
        ids = [row.source_id for row in evidence[:8]] if complete else []
        quests.append({"code": quest.code, "branch": quest.branch,
                       "target": quest.target, "progress": min(quest.target, current),
                       "prerequisite": quest.prerequisite, "state": state,
                       "applicable": bool(applicable), "source_ids": ids,
                       "last_evidence_sequence": max((row.sequence for row in evidence[:8]), default=None)
                       if complete else None})
    # Fingerprint includes identity, credit and progress, never content or URL.
    credits = [{"source_id": row.source_id, "sequence": row.sequence,
                "reward_milli": int(round(row.reward * 1000)), "accepted": row.accepted}
               for row in rows]
    return {
        "schema": SCHEMA,
        "completed": len(unlocked), "total": len(QUESTS),
        "quests": quests,
        "contribution_count": len(rows), "credited_sources": len(useful),
        "revision_digest": hashlib.sha256(_canonical({"credits": credits, "quests": quests})).hexdigest(),
        "derived_not_persisted": True, "training_permission": False,
        "network_authority_expanded": False,
    }
