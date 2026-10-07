"""Query helpers over OmniFabric hot tail and catalogs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Sequence

from skeleton.kernel.omnifabric.core import OmniFabric
from skeleton.kernel.omnifabric.errors import QueryBoundsError
from skeleton.kernel.omnifabric.events import FabricEvent

Predicate = Callable[[FabricEvent], bool]

MAX_LIMIT = 10_000


@dataclass
class QueryResult:
    events: list[FabricEvent]
    truncated: bool = False
    scanned: int = 0

    def to_dicts(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self.events]


def _clamp_limit(limit: int) -> int:
    if limit < 0:
        raise QueryBoundsError("limit must be >= 0")
    if limit > MAX_LIMIT:
        raise QueryBoundsError(f"limit {limit} exceeds max {MAX_LIMIT}")
    return limit


def filter_events(
    events: Sequence[FabricEvent],
    *,
    ledger: str | None = None,
    kind: str | None = None,
    min_seq: int | None = None,
    max_seq: int | None = None,
    attester: str | None = None,
    since_ts: float | None = None,
    until_ts: float | None = None,
    predicate: Predicate | None = None,
    limit: int = 128,
    newest_first: bool = True,
) -> QueryResult:
    limit = _clamp_limit(limit)
    ordered = sorted(events, key=lambda e: e.seq, reverse=newest_first)
    out: list[FabricEvent] = []
    scanned = 0
    truncated = False
    for ev in ordered:
        scanned += 1
        if ledger is not None and ev.ledger != ledger:
            continue
        if kind is not None and ev.kind != kind:
            continue
        if min_seq is not None and ev.seq < min_seq:
            continue
        if max_seq is not None and ev.seq > max_seq:
            continue
        if attester is not None and attester not in ev.quorum:
            continue
        if since_ts is not None and ev.ts < since_ts:
            continue
        if until_ts is not None and ev.ts > until_ts:
            continue
        if predicate is not None and not predicate(ev):
            continue
        out.append(ev)
        if len(out) >= limit:
            truncated = scanned < len(ordered)
            break
    return QueryResult(events=out, truncated=truncated, scanned=scanned)


def query_fabric(fabric: OmniFabric, **kwargs: Any) -> QueryResult:
    return filter_events(fabric.snapshot_tail(), **kwargs)


def range_by_seq(fabric: OmniFabric, start: int, end: int) -> list[FabricEvent]:
    if start > end:
        raise QueryBoundsError("start must be <= end")
    return filter_events(
        fabric.snapshot_tail(),
        min_seq=start,
        max_seq=end,
        limit=min(MAX_LIMIT, end - start + 1),
        newest_first=False,
    ).events
