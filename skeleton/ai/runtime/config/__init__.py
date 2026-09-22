"""
Skeleton Config Package

Exports:
- SettingsSnapshotBridge: Save/restore config snapshots
- ConfigSnapshot: Immutable config capture
"""

from skeleton.config.settings import Settings, get_settings
from skeleton.config.snapshots import ConfigSnapshot, SettingsSnapshotBridge

__all__ = [
    "ConfigSnapshot",
    "Settings",
    "SettingsSnapshotBridge",
    "get_settings",
]
