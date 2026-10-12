"""Compatibility shim — re-exports `skeleton.shells.ai.release_channel`.

This shim exists so callers of `skeleton.ai.shell.release_channel` keep working while `skeleton.shells.ai.release_channel` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.release_channel import (
    ReleaseChannelState,
    ReleaseChannelConflict,
    AIReleaseChannelStore,
)

__all__ = ['ReleaseChannelState', 'ReleaseChannelConflict', 'AIReleaseChannelStore']
