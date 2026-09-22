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
