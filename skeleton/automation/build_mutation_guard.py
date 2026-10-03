"""Reject validation-time mutation outside the exact candidate snapshot."""
from __future__ import annotations
from .build_worktree_snapshot import WorktreeSnapshot
def require_unchanged(before:WorktreeSnapshot,after:WorktreeSnapshot)->None:
 if before.digest()!=after.digest():raise ValueError("validation mutated candidate worktree")
