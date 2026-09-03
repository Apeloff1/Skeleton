"""Hoag-mirror internal knowledge — five brains, codec, decoder, librarians."""
from skeleton.galaxy.atoms import KINDS, TIERS, Atom, house_dialect
from skeleton.galaxy.codec import KnowledgeCodec
from skeleton.galaxy.decoder import KnowledgeDecoder
from skeleton.galaxy.hoag import BRAINS, HOAG_CITE, color_of, galaxy_card
from skeleton.galaxy.librarians import LibrarianMesh, WikiLibrarian
from skeleton.galaxy.mirrors import bind_mouth, mouth_mirrors

__all__ = [
    "Atom",
    "KINDS",
    "TIERS",
    "house_dialect",
    "KnowledgeCodec",
    "KnowledgeDecoder",
    "BRAINS",
    "HOAG_CITE",
    "color_of",
    "galaxy_card",
    "LibrarianMesh",
    "WikiLibrarian",
    "mouth_mirrors",
    "bind_mouth",
    "GalaxySystem",
    "live_galaxy",
    "reset_galaxy",
]


def __getattr__(name: str):
    if name in {"GalaxySystem", "live_galaxy", "reset_galaxy"}:
        from skeleton.galaxy import system as _system
        return getattr(_system, name)
    raise AttributeError(name)
