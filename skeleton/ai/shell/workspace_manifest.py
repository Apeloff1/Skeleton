"""Compatibility shim — re-exports `skeleton.shells.ai.workspace_manifest`.

This shim exists so callers of `skeleton.ai.shell.workspace_manifest` keep working while `skeleton.shells.ai.workspace_manifest` remains the implementation owner. It delegates into the canonical owner and must not grow a second implementation. See issue #80 and docs/CANONICAL_MODULE_BOUNDARIES.md."""

from __future__ import annotations

from skeleton.shells.ai.workspace_manifest import (
    WorkspaceEntryKind,
    WorkspaceEntry,
    WorkspaceManifest,
    WorkspaceDrift,
    WorkspaceManifestComparator,
)

__all__ = ['WorkspaceEntryKind', 'WorkspaceEntry', 'WorkspaceManifest', 'WorkspaceDrift', 'WorkspaceManifestComparator']
