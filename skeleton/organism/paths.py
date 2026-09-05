"""On-disk shelves for the organism. Pointers and cards only.

Path helpers intentionally avoid importing skeleton.cortex so policy_state /
policy_enforcement can load without cortex↔intelligence import cycles.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

ROOT_NAME = "skeleton/acquired"


def _repo_root(start: Optional[Path] = None) -> Path:
    here = Path(start or Path(__file__).resolve())
    for p in [here, *here.parents]:
        if (p / "skeleton" / "cortex").is_dir() and (p / "tests").is_dir():
            return p
    return Path.cwd()


def acquired_base(root: Optional[Path] = None) -> Path:
    """Same layout as cortex.acquire_repo.acquired_dir, without importing cortex."""
    d = (root or _repo_root()) / ROOT_NAME
    (d / "gaming").mkdir(parents=True, exist_ok=True)
    (d / "gates").mkdir(parents=True, exist_ok=True)
    (d / "genos").mkdir(parents=True, exist_ok=True)
    return d


def organism_dir(root: Optional[Path] = None) -> Path:
    d = acquired_base(root) / "organism"
    d.mkdir(parents=True, exist_ok=True)
    return d


def state_path(root: Optional[Path] = None) -> Path:
    return organism_dir(root) / "state.json"


def ledger_path(root: Optional[Path] = None) -> Path:
    return organism_dir(root) / "ledger.jsonl"


def galaxy_path(root: Optional[Path] = None) -> Path:
    return organism_dir(root) / "galaxy.json"


def helix_sense_path(root: Optional[Path] = None) -> Path:
    return organism_dir(root) / "helix_sense.jsonl"


def helix_snap_path(root: Optional[Path] = None) -> Path:
    return organism_dir(root) / "helix_snap.jsonl"


def kv_path(root: Optional[Path] = None) -> Path:
    return organism_dir(root) / "kv.json"


def quality_path(root: Optional[Path] = None) -> Path:
    return organism_dir(root) / "quality.jsonl"
