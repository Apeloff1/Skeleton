"""Promotion sink that bridges verified absorb snapshots into RagMemory."""

from __future__ import annotations

from dataclasses import dataclass

from .absorb import KnowledgeSnapshot, SnapshotEntry
from .rag import RagMemory


@dataclass(slots=True)
class SnapshotRagSink:
    """Write only newly promoted snapshot entries to the retrieval store.

    The sink is invoked after an immutable snapshot has been published.  Raw,
    deferred and quarantined observations therefore never enter live RAG.
    """

    memory: RagMemory

    def __call__(
        self,
        snapshot: KnowledgeSnapshot,
        entries: tuple[SnapshotEntry, ...],
    ) -> None:
        for entry in entries:
            self.memory.remember(
                entry.canonical_content,
                metadata={
                    "absorb_snapshot": snapshot.version,
                    "absorb_digest": snapshot.digest,
                    "observation_id": entry.observation_id,
                    "source_id": entry.source_id,
                    "knowledge_tier": entry.target_tier,
                    "confidence": entry.confidence,
                    "journal_offset": entry.journal_offset,
                },
            )
