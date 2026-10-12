"""Compatibility shim — re-exports `skeleton.shells.ai.durable_hot_floor`.

This shim exists so callers of `skeleton.ai.shell.durable_hot_floor` keep working while `skeleton.shells.ai.durable_hot_floor` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.durable_hot_floor import (
    GENESIS_HASH,
    DurableHotFloor,
    SignedDurableHotFloor,
    HotFloorPosition,
    DurableHotFloorHistoryIndex,
    DurableHotFloorHistoryReport,
    DurableHotFloorError,
    DurableHotFloorStore,
)

__all__ = ['GENESIS_HASH', 'DurableHotFloor', 'SignedDurableHotFloor', 'HotFloorPosition', 'DurableHotFloorHistoryIndex', 'DurableHotFloorHistoryReport', 'DurableHotFloorError', 'DurableHotFloorStore']
