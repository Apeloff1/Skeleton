"""Durable AI decision journal over the content-addressed evidence chain."""

from __future__ import annotations

import time
from typing import Callable, Mapping

from skeleton.shells.ai.journal import AIDecisionEvent, AIDecisionJournal
from skeleton.shells.evidence_chain import (
    ContentAddressedEvidenceChain,
    EvidenceCorruption,
    EvidenceStateBackend,
    GENESIS_HASH,
)


class DistributedAIDecisionJournal:
    """AIDecisionJournal-compatible durable journal.

    Timestamps use wall-clock time because committed events may be read by a
    different host after restart.
    """

    GENESIS = GENESIS_HASH

    def __init__(
        self,
        backend: EvidenceStateBackend,
        *,
        namespace: str = "shell-ai-decision-journal",
        max_events: int = 100_000,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.max_events = max_events
        self._clock = clock
        self._chain = ContentAddressedEvidenceChain(
            backend,
            namespace=namespace,
            max_events=max_events,
        )

    def append(
        self,
        kind: str,
        *,
        session_id: str,
        intent_id: str,
        proposal_id: str = "",
        summary: str = "",
        data: Mapping[str, object] | None = None,
    ) -> AIDecisionEvent:
        if not kind or len(kind) > 128:
            raise ValueError("invalid AI decision event kind")
        if len(summary) > 2048:
            raise ValueError("AI decision summary too long")
        payload_data = dict(data or {})
        if len(payload_data) > 128:
            raise ValueError("too many AI decision data fields")
        observed_at = self._clock()
        outer = self._chain.append(
            "ai.decision.event",
            {
                "kind": kind,
                "observed_at": observed_at,
                "session_id": session_id,
                "intent_id": intent_id,
                "proposal_id": proposal_id,
                "summary": summary,
                "data": payload_data,
            },
        )
        # Rebuild the original journal hash chain independently of the outer
        # content-addressed storage chain so existing replay semantics survive.
        events = self.snapshot()
        return events[outer.sequence - 1]

    def snapshot(self) -> tuple[AIDecisionEvent, ...]:
        nodes = self._chain.snapshot()
        result = []
        previous = self.GENESIS
        for sequence, node in enumerate(nodes, start=1):
            payload = dict(node.payload)
            try:
                kind = str(payload["kind"])
                observed_at = float(payload["observed_at"])
                session_id = str(payload["session_id"])
                intent_id = str(payload["intent_id"])
                proposal_id = str(payload.get("proposal_id", ""))
                summary = str(payload.get("summary", ""))
                data = dict(payload.get("data", {}))
            except (KeyError, TypeError, ValueError) as exc:
                raise EvidenceCorruption("durable AI journal payload is invalid") from exc
            event_hash = AIDecisionJournal._hash(
                previous,
                sequence,
                kind,
                observed_at,
                session_id,
                intent_id,
                proposal_id,
                summary,
                data,
            )
            result.append(
                AIDecisionEvent(
                    sequence,
                    previous,
                    event_hash,
                    kind,
                    observed_at,
                    session_id,
                    intent_id,
                    proposal_id,
                    summary,
                    data,
                )
            )
            previous = event_hash
        return tuple(result)

    def verify(self) -> bool:
        if not self._chain.verify():
            return False
        try:
            events = self.snapshot()
        except (EvidenceCorruption, ValueError):
            return False
        previous = self.GENESIS
        for sequence, event in enumerate(events, start=1):
            if event.sequence != sequence or event.previous_hash != previous:
                return False
            expected = AIDecisionJournal._hash(
                previous,
                sequence,
                event.kind,
                event.observed_at,
                event.session_id,
                event.intent_id,
                event.proposal_id,
                event.summary,
                event.data,
            )
            if event.event_hash != expected:
                return False
            previous = event.event_hash
        return True

    def root_hash(self) -> str:
        items = self.snapshot()
        return items[-1].event_hash if items else self.GENESIS
