"""Typed-frame evidence for frontier GPS, chunks, edits, telemetry, and recorder sessions.

Hashing and frame verification stay with the canonical frame-coherence and
chunk-evidence helpers. This package does not qualify consoles, GPUs, or devices.
"""

from skeleton.frontier_evidence.common import EvidenceRejected, content_digest, seal, seal_ok
from skeleton.frontier_evidence.edits import (
    SOURCE_KINDS,
    ChunkTouch,
    SourceRef,
    WorldEdit,
    seal_world_edit,
    verify_edit_chain,
    verify_world_edit,
)
from skeleton.frontier_evidence.eras import (
    EraChunkAdapter,
    adapter_for,
    registered_adapters,
)
from skeleton.frontier_evidence.feed import (
    ENGINE_CONSOLE,
    ReceiptPositionSource,
    feed_typed_frames,
    registered_era_lanes,
)
from skeleton.frontier_evidence.recorder import RecorderSession, RecorderSessionError, start
from skeleton.frontier_evidence.telemetry import (
    CHANNELS,
    TelemetryAdapter,
    TelemetryRejected,
    adapters_for_era,
    ingest_sample,
)

__all__ = [
    "CHANNELS",
    "ENGINE_CONSOLE",
    "SOURCE_KINDS",
    "ChunkTouch",
    "EraChunkAdapter",
    "EvidenceRejected",
    "ReceiptPositionSource",
    "RecorderSession",
    "RecorderSessionError",
    "SourceRef",
    "TelemetryAdapter",
    "TelemetryRejected",
    "WorldEdit",
    "adapter_for",
    "adapters_for_era",
    "content_digest",
    "feed_typed_frames",
    "ingest_sample",
    "registered_adapters",
    "registered_era_lanes",
    "seal",
    "seal_ok",
    "seal_world_edit",
    "start",
    "verify_edit_chain",
    "verify_world_edit",
]
