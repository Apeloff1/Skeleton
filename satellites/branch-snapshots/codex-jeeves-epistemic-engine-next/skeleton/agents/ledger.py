"""Append-only agent activity ledger.

The ledger is the single source of audit truth for everything agents and
pipelines do. Every meaningful act — a stage completing, a quorum won, a
materialisation — appends a :class:`LedgerEntry`. Storage is a bounded deque
(oldest entries evicted past capacity) with secondary indexes for the three
cardinal query shapes: by agent, by action, by time window.

Design notes
------------
- Append is O(1); query performance is proportional to the number of matches,
  not the ledger size, thanks to the per-agent and per-action indexes.
- Eviction from the deque also purges the secondary indexes, so memory stays
  bounded regardless of query history.
- Entries are immutable; the ledger is the only writer.
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Iterable

from skeleton.kernel.ids import AgentId


@dataclass(frozen=True)
class LedgerEntry:
    """One immutable fact in the activity ledger."""

    agent_id: AgentId
    action: str
    detail: dict[str, Any]
    outcome: str = "success"  # "success" | "failure" | "info"
    correlation_id: str | None = None
    entry_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    occurred_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "agent_id": str(self.agent_id),
            "action": self.action,
            "detail": self.detail,
            "outcome": self.outcome,
            "correlation_id": self.correlation_id,
            "occurred_at": self.occurred_at,
        }


@dataclass(frozen=True)
class AgentSummary:
    """Aggregate statistics for one agent, derived from the ledger."""

    agent_id: AgentId
    total_actions: int
    successes: int
    failures: int
    distinct_actions: int
    first_seen: float
    last_seen: float
    top_actions: tuple[tuple[str, int], ...]

    @property
    def success_rate(self) -> float:
        decided = self.successes + self.failures
        return self.successes / decided if decided else 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": str(self.agent_id),
            "total_actions": self.total_actions,
            "successes": self.successes,
            "failures": self.failures,
            "success_rate": round(self.success_rate, 4),
            "distinct_actions": self.distinct_actions,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "top_actions": [{"action": a, "count": c} for a, c in self.top_actions],
        }


class ActivityLedger:
    """Bounded append-only ledger with indexed queries."""

    def __init__(self, *, capacity: int = 100_000) -> None:
        self._entries: deque[LedgerEntry] = deque(maxlen=capacity)
        self._by_agent: dict[AgentId, deque[LedgerEntry]] = defaultdict(deque)
        self._by_action: dict[str, deque[LedgerEntry]] = defaultdict(deque)
        self._capacity = capacity

    # -- writing -------------------------------------------------------------

    def append(
        self,
        agent_id: AgentId,
        action: str,
        detail: dict[str, Any] | None = None,
        *,
        outcome: str = "success",
        correlation_id: str | None = None,
    ) -> LedgerEntry:
        """Append an entry. The only mutator; entries are never edited."""
        entry = LedgerEntry(
            agent_id=agent_id,
            action=action,
            detail=detail or {},
            outcome=outcome,
            correlation_id=correlation_id,
        )
        self._append_entry(entry)
        return entry

    def append_entry(self, entry: LedgerEntry) -> LedgerEntry:
        """Append a pre-built entry (used by importers/replay)."""
        self._append_entry(entry)
        return entry

    def _append_entry(self, entry: LedgerEntry) -> None:
        if len(self._entries) == self._capacity:
            evicted = self._entries[0]
            self._purge_from_indexes(evicted)
        self._entries.append(entry)
        self._by_agent[entry.agent_id].append(entry)
        self._by_action[entry.action].append(entry)

    def _purge_from_indexes(self, evicted: LedgerEntry) -> None:
        agent_index = self._by_agent.get(evicted.agent_id)
        if agent_index is not None:
            try:
                agent_index.remove(evicted)
            except ValueError:
                pass
            if not agent_index:
                del self._by_agent[evicted.agent_id]
        action_index = self._by_action.get(evicted.action)
        if action_index is not None:
            try:
                action_index.remove(evicted)
            except ValueError:
                pass
            if not action_index:
                del self._by_action[evicted.action]

    # -- reading -------------------------------------------------------------

    def query(
        self,
        *,
        agent_id: AgentId | None = None,
        action: str | None = None,
        outcome: str | None = None,
        since: float | None = None,
        until: float | None = None,
        correlation_id: str | None = None,
        limit: int | None = None,
    ) -> list[LedgerEntry]:
        """Composable query. The most selective available index is used as the
        candidate set; remaining filters are applied in a single pass."""
        if agent_id is not None:
            candidates: Iterable[LedgerEntry] = self._by_agent.get(agent_id, ())
        elif action is not None:
            candidates = self._by_action.get(action, ())
        else:
            candidates = self._entries

        results: list[LedgerEntry] = []
        for entry in candidates:
            if agent_id is not None and entry.agent_id != agent_id:
                continue
            if action is not None and entry.action != action:
                continue
            if outcome is not None and entry.outcome != outcome:
                continue
            if since is not None and entry.occurred_at < since:
                continue
            if until is not None and entry.occurred_at > until:
                continue
            if correlation_id is not None and entry.correlation_id != correlation_id:
                continue
            results.append(entry)
            if limit is not None and len(results) >= limit:
                break
        return results

    def tail(self, n: int = 50) -> list[LedgerEntry]:
        """Most recent n entries, newest first."""
        if n <= 0:
            return []
        entries = list(self._entries)
        return entries[::-1][:n]

    def for_correlation(self, correlation_id: str) -> list[LedgerEntry]:
        """All entries in one causal chain, chronological."""
        return self.query(correlation_id=correlation_id)

    # -- aggregation -----------------------------------------------------------

    def summarise(self, agent_id: AgentId) -> AgentSummary:
        entries = self._by_agent.get(agent_id)
        if not entries:
            now = time.time()
            return AgentSummary(
                agent_id=agent_id,
                total_actions=0,
                successes=0,
                failures=0,
                distinct_actions=0,
                first_seen=now,
                last_seen=now,
                top_actions=(),
            )
        action_counts: dict[str, int] = defaultdict(int)
        successes = failures = 0
        for e in entries:
            action_counts[e.action] += 1
            if e.outcome == "success":
                successes += 1
            elif e.outcome == "failure":
                failures += 1
        top = sorted(action_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        return AgentSummary(
            agent_id=agent_id,
            total_actions=len(entries),
            successes=successes,
            failures=failures,
            distinct_actions=len(action_counts),
            first_seen=entries[0].occurred_at,
            last_seen=entries[-1].occurred_at,
            top_actions=tuple(top),
        )

    def action_histogram(self) -> dict[str, int]:
        """Count per action across the whole retained ledger."""
        return {action: len(entries) for action, entries in self._by_action.items()}

    def agent_ids(self) -> list[AgentId]:
        return sorted(self._by_agent.keys())

    def stats(self) -> dict[str, Any]:
        return {
            "entries": len(self._entries),
            "capacity": self._capacity,
            "distinct_agents": len(self._by_agent),
            "distinct_actions": len(self._by_action),
        }

    def __len__(self) -> int:
        return len(self._entries)
