"""Agent librarians — one per brain, all wired to the wiki librarian.

A librarian owns a shelf (atom bank), answers queries, writes
provenance, and never stores third-party prose. The wiki librarian
is the nucleus: it holds the master catalog of topics and citations.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from skeleton.galaxy.atoms import Atom, jaccard, token_set
from skeleton.galaxy.hoag import color_of


class Librarian:
    def __init__(self, brain: str) -> None:
        self.brain = brain
        self.color = color_of(brain)
        self.shelf: Dict[str, Atom] = {}
        self.log: List[str] = []

    def shelve(self, atom: Atom) -> Atom:
        self.shelf[atom.id] = atom
        self.log.append(atom.id)
        return atom

    def get(self, aid: str) -> Optional[Atom]:
        return self.shelf.get(aid)

    def search(self, query: str, *, k: int = 8) -> List[Atom]:
        q = token_set(query)
        scored = sorted(
            self.shelf.values(),
            key=lambda a: (jaccard(q, a.tokens) * a.confidence, a.ts),
            reverse=True,
        )
        return [a for a in scored[:k] if not a.superseded_by]

    def all(self) -> List[Atom]:
        return list(self.shelf.values())

    def card(self) -> Dict[str, Any]:
        return {
            "brain": self.brain,
            "color": self.color,
            "size": len(self.shelf),
            "writes": len(self.log),
            "stored_prose": 0,
        }


class WikiLibrarian(Librarian):
    """Nucleus. Topic → citation index. Every brain librarian reports here."""

    def __init__(self) -> None:
        super().__init__("wiki")
        self.topics: Dict[str, str] = {}
        self.reports: List[Dict[str, Any]] = []

    def register_topic(self, topic: str, citation: str = "") -> None:
        key = " ".join(token_set(topic)[:6])
        if key:
            self.topics[key] = citation

    def hear(self, librarian: Librarian, atom: Atom) -> None:
        self.shelve(atom)
        self.register_topic(atom.topic, atom.citation)
        self.reports.append({
            "from": librarian.brain,
            "atom": atom.id,
            "tier": atom.tier,
            "color": librarian.color,
        })

    def catalog(self) -> Dict[str, Any]:
        return {
            "topics": dict(self.topics),
            "reports": len(self.reports),
            "nucleus": self.card(),
            "stored_prose": 0,
        }


class LibrarianMesh:
    """Five brain librarians + wiki nucleus."""

    def __init__(self) -> None:
        self.wiki = WikiLibrarian()
        self.brains = {
            name: Librarian(name)
            for name in ("memory", "compiler", "dream", "distiller", "editor")
        }

    def of(self, brain: str) -> Librarian:
        if brain == "wiki":
            return self.wiki
        if brain not in self.brains:
            raise KeyError(brain)
        return self.brains[brain]

    def publish(self, atom: Atom) -> Atom:
        lib = self.of(atom.brain if atom.brain in self.brains else "memory")
        lib.shelve(atom)
        self.wiki.hear(lib, atom)
        return atom

    def broadcast_search(self, query: str, *, k: int = 4) -> List[Atom]:
        hits: List[Atom] = []
        for lib in self.brains.values():
            hits.extend(lib.search(query, k=k))
        hits.extend(self.wiki.search(query, k=k))
        seen = set()
        uniq: List[Atom] = []
        for a in hits:
            if a.id in seen:
                continue
            seen.add(a.id)
            uniq.append(a)
        return uniq

    def to_dict(self) -> Dict[str, Any]:
        return {
            "wiki": self.wiki.catalog(),
            "brains": {n: l.card() for n, l in self.brains.items()},
            "stored_prose": 0,
        }
