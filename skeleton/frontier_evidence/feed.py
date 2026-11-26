"""Feed canonical typed frames into the frontier GPS hub.

``FrameReceipt`` values are the typed frames. Positions and claimed chunk
membership are handed to :meth:`FrameGPSHub.accept_frames`. A missing frame
fails closed. The lane era must be one of the registered engine eras.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from skeleton.frontier_nav.gps import (
    FrameFix,
    FrameGPSHub,
    NavigationCursor,
    TypedFrame,
)
from skeleton.jeeves.game_engine_lab import ERA_PROFILES, EngineEra
from skeleton.jeeves.game_frontier_frame_coherence import FrameReceipt

from skeleton.frontier_evidence.common import EvidenceRejected
from skeleton.frontier_evidence.eras import adapter_for

ENGINE_CONSOLE = "engine"


def registered_era_lanes(console: str = ENGINE_CONSOLE) -> frozenset[tuple[str, str]]:
    if not isinstance(console, str) or not console:
        raise EvidenceRejected("console lane name required")
    return frozenset((console, era.value) for era in EngineEra if era in ERA_PROFILES)


class ReceiptPositionSource:
    """:class:`FramePositionSource` backed by typed ``FrameReceipt`` values."""

    def __init__(
        self,
        console: str,
        era: str,
        frames: Sequence[FrameReceipt | None],
        chunk_size_m: float = 32.0,
    ) -> None:
        if not isinstance(console, str) or not console or not isinstance(era, str) or not era:
            raise EvidenceRejected("console and era required")
        self.console = console
        self.era = era
        self._frames = tuple(frames)
        self.chunk_size_m = chunk_size_m

    def frames(self) -> Iterable[TypedFrame]:
        for frame in self._frames:
            if not isinstance(frame, FrameReceipt):
                raise EvidenceRejected("missing frame")
            fixes = tuple(
                FrameFix(
                    entity_id=obj.entity_id,
                    x=obj.position.x,
                    y=obj.position.y,
                    z=obj.position.z,
                    chunk_xy=tuple(chunk.chunk_key),
                )
                for chunk in frame.chunks
                for obj in chunk.objects
            )
            yield TypedFrame(self.console, self.era, frame.frame_index, fixes, self.chunk_size_m)


def feed_typed_frames(
    hub: FrameGPSHub,
    era: EngineEra | str,
    frames: Sequence[FrameReceipt | None],
    *,
    console: str = ENGINE_CONSOLE,
    chunk_size_m: float = 32.0,
) -> tuple[NavigationCursor, ...]:
    """Adapt registered-era typed frames onto the authoritative GPS hub."""
    if not isinstance(hub, FrameGPSHub):
        raise EvidenceRejected("FrameGPSHub required")
    selected = adapter_for(era)
    if any(not isinstance(frame, FrameReceipt) for frame in frames):
        raise EvidenceRejected("missing frame")
    source = ReceiptPositionSource(console, selected.era.value, frames, chunk_size_m)
    return hub.accept_frames(source)
