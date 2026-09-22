"""On-disk books under acquired/organism/chronicle/. Gitignored."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from skeleton.organism.paths import organism_dir

HORIZON_YEARS = 10
HOT_BYTES = 4 * 1024 * 1024
MONTH_LINES = 12_000


def root(root: Optional[Path] = None) -> Path:
    d = organism_dir(root) / "chronicle"
    d.mkdir(parents=True, exist_ok=True)
    return d


def rolodex_path(root_: Optional[Path] = None) -> Path:
    return root(root_) / "rolodex.json"


def itinerary_path(root_: Optional[Path] = None) -> Path:
    return root(root_) / "itinerary.jsonl"


def index_path(root_: Optional[Path] = None) -> Path:
    return root(root_) / "index.json"


def manifest_path(root_: Optional[Path] = None) -> Path:
    return root(root_) / "MANIFEST.jsonl"


def annals_dir(year: int, month: int, *, root_: Optional[Path] = None) -> Path:
    d = root(root_) / "annals" / f"{int(year):04d}" / f"{int(month):02d}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def annals_path(year: int, month: int, *, root_: Optional[Path] = None) -> Path:
    return annals_dir(year, month, root_=root_) / "roll.jsonl"


def backup_dir(year: int, *, root_: Optional[Path] = None) -> Path:
    d = root(root_) / "backup" / f"{int(year):04d}"
    d.mkdir(parents=True, exist_ok=True)
    return d
