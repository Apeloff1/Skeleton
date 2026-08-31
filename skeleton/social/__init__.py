"""Social SOTA layer — ArchiveX, Wayback, arXiv, lab pointers. No prose."""
from skeleton.social.archivex import parse_x_status, pointer
from skeleton.social.ingest import ingest, seed_sota
from skeleton.social.sota import sota_card
from skeleton.social.sources import SOURCES, catalog, classify

__all__ = [
    "SOURCES",
    "catalog",
    "classify",
    "parse_x_status",
    "pointer",
    "ingest",
    "seed_sota",
    "sota_card",
]
