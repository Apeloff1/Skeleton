"""On-disk shelves for the organism. Pointers and cards only."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from skeleton.cortex.acquire_repo import acquired_dir


def organism_dir(root: Optional[Path] = None) -> Path:
    d = acquired_dir(root) / "organism"
    d.mkdir(parents=True, exist_ok=True)
    return d


def state_path(root: Optional[Path] = None) -> Path:
    return organism_dir(root) / "state.json"


def ledger_path(root: Optional[Path] = None) -> Path:
    return organism_dir(root) / "ledger.jsonl"


def galaxy_path(root: Optional[Path] = None) -> Path:
    return organism_dir(root) / "galaxy.json"
