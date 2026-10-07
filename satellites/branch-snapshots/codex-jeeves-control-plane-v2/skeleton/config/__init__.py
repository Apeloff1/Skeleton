"""
Skeleton Config Package

Exports:
- SettingsSnapshotBridge: Save/restore config snapshots
- ConfigSnapshot: Immutable config capture
"""

from skeleton.config.snapshots import ConfigSnapshot, SettingsSnapshotBridge

__all__ = ["ConfigSnapshot", "SettingsSnapshotBridge"]
