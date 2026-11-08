"""Source-anchored document-date evidence without inferred remote freshness.

Only explicit ISO-like year/month/day tokens appearing in current retained
research passages are represented, with exact Unicode spans and the original
source revision. Capture time is provenance, not evidence that the mentioned
event happened at that time or that the remote website remains current.

The timeline is a compact review aid; dates are lexical observations and
never silently become authoritative event timestamps or schedules.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date
from hashlib import sha256
from typing import Iterable
import re

from ..operations import CrawlRun
from .contracts import CampaignMandate, digest, ensure_snapshot_scope, integer
from .policy_matrix import SourcePolicyProjection
from .retrieval_fusion import RetrievalFusion

_DATE = re.compile(
    r"(?<![\w-])(?P<y>(?:1[0-9]{3}|20[0-9]{2}|2100))"
    r"-(?P<m>0[1-9]|1[0-2])-(?P<d>0[1-9]|[12]\d|3[01])(?![\w-])"
)
_LABELS = (
    ("as_of", re.compile(r"\bas\s+of\b", re.I)),
    ("updated", re.compile(r"\bupdated?\b", re.I)),
    ("published", re.compile(r"\bpublished?\b", re.I)),
    ("revised", re.compile(r"\brevised?\b", re.I)),
    ("historical_reference", re.compile(r"\b(?:in|since|during|after|before)\b", re.I)),
)


@dataclass(frozen=True)
class TemporalMention:
    source_id: str
    source_hash: str
    passage_hash: str
    canonical_url: str
    year: int
    month: int
    day: int
    iso_date: str
    start: int
    end: int
    retained_text: str
    context_label: str
    captured_at: float
    objective_ids: tuple[str, ...]
    asserted_remote_freshness: bool = False
    externally_reviewed: bool = False


@dataclass(frozen=True)
class TemporalNeighborhood:
    iso_date: str
    objective_id: str
    source_ids: tuple[str, ...]
    mentions: int
    earliest_capture_at: float
    latest_capture_at: float
    independent_provenance_established: bool = False


@dataclass(frozen=True)
class TemporalSignalReport:
    mandate_digest: str
    source_snapshot_digest: str
    source_policy_digest: str
    retrieval_digest: str
    mentions: tuple[TemporalMention, ...]
    date_groups: tuple[TemporalNeighborhood, ...]
    rejected_invalid_dates: int
    examined_passages: int
    signal_digest: str
    actual_remote_update_checked: bool = False
    event_ontology_verified: bool = False


def _context_label(text: str, position: int) -> str:
    prefix = text[max(0, position - 50):position]
    for name, expression in _LABELS:
        if expression.search(prefix):
            return name
    return "unclassified_date_mention"


def detect_temporal_mentions(
    mandate: CampaignMandate,
    snapshot: dict[str, object],
    policy: SourcePolicyProjection,
    retrieval: RetrievalFusion,
    *,
    now: float,
    authorized: bool,
    max_mentions: int = 256,
    max_date_groups: int = 256,
) -> TemporalSignalReport:
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    integer(max_mentions, "temporal evidence cap", 1, 512)
    integer(max_date_groups, "temporal group cap", 1, 512)
    if policy.mandate_digest != mandate.fingerprint or (
        retrieval.mandate_digest != mandate.fingerprint
    ):
        raise PermissionError("temporal source belongs to another mandate")
    current = CrawlRun.from_snapshot(snapshot).snapshot()
    if policy.source_snapshot_digest != current["snapshot_digest"] or (
        retrieval.source_snapshot_digest != current["snapshot_digest"]
        or retrieval.excluded_sources != policy.excluded_source_ids
    ):
        raise PermissionError("temporal evidence uses stale source policy")
    accepted = set(policy.allowed_source_ids)
    observed, keys = [], set()
    invalid = 0
    for hit in retrieval.results:
        source = current["sources"].get(hit.source_id)
        if source is None or hit.source_id not in accepted:
            raise PermissionError("unavailable temporal source")
        text = source["text"]
        if (
            source["canonical_url"] != hit.canonical_url
            or source["content_hash"] != hit.source_hash
            or source["text_truncated"] is not False
            or source["review_state"] != "unreviewed"
            or sha256(text.encode("utf-8")).hexdigest() != source["preserved_text_hash"]
            or text[hit.start:hit.end] != hit.text
            or sha256(hit.text.encode("utf-8")).hexdigest() != hit.passage_hash
        ):
            raise PermissionError("temporal source hash or passage integrity mismatch")
        for match in _DATE.finditer(hit.text):
            year, month, day = map(int, match.group("y", "m", "d"))
            try:
                actual = date(year, month, day)
            except ValueError:
                invalid += 1
                continue
            start, end = hit.start + match.start(), hit.start + match.end()
            identity = hit.source_id, start, end
            if identity in keys:
                continue
            if len(observed) >= max_mentions:
                raise ValueError("temporal mentions exceed bounded memory")
            keys.add(identity)
            observed.append(TemporalMention(
                source_id=hit.source_id, source_hash=hit.source_hash,
                passage_hash=hit.passage_hash,
                canonical_url=hit.canonical_url,
                year=year, month=month, day=day, iso_date=actual.isoformat(),
                start=start, end=end,
                retained_text=match.group(),
                context_label=_context_label(hit.text, match.start()),
                captured_at=source["fetched_at"],
                objective_ids=hit.matched_objective_ids,
            ))
    observed.sort(key=lambda x: (
        x.iso_date, x.source_id, x.start, x.end
    ))
    by_date = defaultdict(list)
    for row in observed:
        for objective_id in row.objective_ids:
            by_date[(row.iso_date, objective_id)].append(row)
    if len(by_date) > max_date_groups:
        raise ValueError("temporal event grouping capacity exceeded")
    groups = tuple(TemporalNeighborhood(
        iso_date=key[0], objective_id=key[1],
        source_ids=tuple(sorted({x.source_id for x in rows})),
        mentions=len(rows),
        earliest_capture_at=min(x.captured_at for x in rows),
        latest_capture_at=max(x.captured_at for x in rows),
    ) for key, rows in sorted(by_date.items()))
    payload = {
        "mandate": mandate.fingerprint,
        "snapshot": current["snapshot_digest"],
        "policy": policy.policy_digest,
        "retrieval": retrieval.fusion_digest,
        "mentions": [asdict(x) for x in observed],
        "grouped": [asdict(x) for x in groups],
        "invalid": invalid,
        "limits": (max_mentions, max_date_groups),
    }
    return TemporalSignalReport(
        mandate_digest=mandate.fingerprint,
        source_snapshot_digest=current["snapshot_digest"],
        source_policy_digest=policy.policy_digest,
        retrieval_digest=retrieval.fusion_digest,
        mentions=tuple(observed), date_groups=groups,
        rejected_invalid_dates=invalid,
        examined_passages=len(retrieval.results),
        signal_digest=digest(payload),
    )
