"""Organism filesystem paths — single source of truth for state files."""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def organism_dir(root: Optional[Path] = None) -> Path:
    """Root directory for organism state (policy, quality ledger)."""
    base = Path(root) if root else Path(".skeleton")
    return base / "organism"


def quality_path(root: Optional[Path] = None) -> Path:
    """JSONL ledger of quality and repair entries."""
    return organism_dir(root) / "quality.jsonl"


def organism_root(root: Optional[Path] = None) -> Path:
    """Compatibility name for the organism's state directory."""
    return organism_dir(root)


def state_path(root: Optional[Path] = None) -> Path:
    return organism_dir(root) / "state.json"


def galaxy_path(root: Optional[Path] = None) -> Path:
    return organism_dir(root) / "galaxy.json"


def kv_path(root: Optional[Path] = None) -> Path:
    return organism_dir(root) / "kv.json"


def ledger_path(root: Optional[Path] = None) -> Path:
    return organism_dir(root) / "ledger.jsonl"


def helix_sense_path(root: Optional[Path] = None) -> Path:
    return organism_dir(root) / "helix_sense.jsonl"


def helix_snap_path(root: Optional[Path] = None) -> Path:
    return organism_dir(root) / "helix_snap.jsonl"
