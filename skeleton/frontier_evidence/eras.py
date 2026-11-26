"""Era adapters that emit chunk evidence from typed frames.

Every era comes from the canonical ``EngineEra`` / ``ERA_PROFILES`` registry.
An adapter reads the frame and runs the existing frame verifiers. Verifier A
is the content hash. Verifier B is topology and chunk membership. A missing
frame fails closed. Nothing here qualifies a console, GPU, or device.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from skeleton.jeeves.game_engine_lab import (
    ERA_PROFILES,
    EngineEra,
    engine_era_profile,
    list_engine_eras,
)
from skeleton.jeeves.game_frontier_chunk_evidence import (
    ChunkEvidenceError,
    build_frame_chunk_receipts,
)
from skeleton.jeeves.game_frontier_frame_coherence import (
    FrameReceipt,
    GDDSource,
    verify_frame,
)

from skeleton.frontier_evidence.common import EvidenceRejected, seal

SCHEMA = "skeleton.frontier_evidence.era_chunk_evidence.v1"


class EraChunkAdapter:
    """Emit chunk evidence for one registered era from a typed frame."""

    def __init__(self, era: EngineEra) -> None:
        if not isinstance(era, EngineEra) or era not in ERA_PROFILES:
            raise EvidenceRejected(f"unknown era: {era!r}")
        engine_era_profile(era)
        self.era = era

    def verify(
        self,
        frame: FrameReceipt | None,
        gdd: GDDSource,
        *,
        previous: FrameReceipt | None = None,
    ) -> tuple[bool, bool]:
        """Run verifier A (content hash) and verifier B (topology/membership)."""
        if frame is None or not isinstance(frame, FrameReceipt):
            raise EvidenceRejected("missing frame")
        if not isinstance(gdd, GDDSource):
            raise EvidenceRejected("signed GDD source required")
        return verify_frame(frame, gdd, previous=previous)

    def emit(
        self,
        frame: FrameReceipt | None,
        gdd: GDDSource,
        *,
        previous: FrameReceipt | None = None,
        previous_evidence: Mapping | None = None,
    ) -> dict:
        """Build chunk evidence from ``frame``. A handwritten estimate is not accepted."""
        verified_a, verified_b = self.verify(frame, gdd, previous=previous)
        if not isinstance(frame, FrameReceipt):
            raise EvidenceRejected("missing frame")
        if not verified_a or not verified_b:
            raise EvidenceRejected(
                f"frame verifiers refused evidence for {self.era.value}: "
                f"content={verified_a} topology={verified_b}"
            )
        try:
            bundle = build_frame_chunk_receipts(
                frame,
                gdd,
                previous=previous,
                previous_evidence=previous_evidence,
            )
        except ChunkEvidenceError as exc:
            raise EvidenceRejected("chunk evidence could not be derived from the frame") from exc
        actors = [
            {
                "entity_id": obj.entity_id,
                "chunk_id": [chunk.chunk_key[0], chunk.chunk_key[1]],
                "frame_index": frame.frame_index,
            }
            for chunk in frame.chunks
            for obj in chunk.objects
        ]
        receipt_keys = [row["chunk_xy"] for row in bundle["receipts"]]
        frame_keys = [[chunk.chunk_key[0], chunk.chunk_key[1]] for chunk in frame.chunks]
        bundle_entities = [entity for row in bundle["receipts"] for entity in row["source_entities"]]
        frame_entities = [obj.entity_id for chunk in frame.chunks for obj in chunk.objects]
        if (
            bundle.get("source_frame_digest") != frame.receipt_digest
            or bundle.get("frame_index") != frame.frame_index
            or receipt_keys != frame_keys
            or bundle_entities != frame_entities
            or [actor["entity_id"] for actor in actors] != frame_entities
        ):
            raise EvidenceRejected("chunk evidence ignored the typed frame")
        return seal(
            {
                "schema": SCHEMA,
                "era": self.era.value,
                "frame_index": frame.frame_index,
                "source_frame_digest": frame.receipt_digest,
                "verifier_a": verified_a,
                "verifier_b": verified_b,
                "actors": actors,
                "chunk_evidence_digest": bundle["receipt_digest"],
                "chunk_evidence": bundle,
                "authority": "frame_derived_chunk_evidence_not_device_qualification",
            }
        )


def _build_registry() -> Mapping[EngineEra, EraChunkAdapter]:
    adapters = {profile.era: EraChunkAdapter(profile.era) for profile in list_engine_eras()}
    if set(adapters) != set(EngineEra) or set(adapters) != set(ERA_PROFILES):
        raise EvidenceRejected("era adapter registry diverges from EngineEra")
    return MappingProxyType(adapters)


REGISTERED_ADAPTERS = _build_registry()


def registered_adapters() -> Mapping[EngineEra, EraChunkAdapter]:
    return REGISTERED_ADAPTERS


def adapter_for(era: EngineEra | str) -> EraChunkAdapter:
    try:
        key = era if isinstance(era, EngineEra) else EngineEra(str(era))
    except (ValueError, TypeError) as exc:
        raise EvidenceRejected(f"unknown era: {era!r}") from exc
    try:
        return REGISTERED_ADAPTERS[key]
    except KeyError as exc:
        raise EvidenceRejected(f"unknown era: {era!r}") from exc
