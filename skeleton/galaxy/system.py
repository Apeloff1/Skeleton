"""GalaxySystem — five brains + codec + decoder + Hoag mirrors.

Pulse order (perpendicular to linear CODE):
  editor.route → memory.ingest → compiler.compile → distiller.glean
  → editor.index → (optional) dream.sleep → decoder.decode
Wiki librarian hears every write. Mouths attach as colored gap rings.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from skeleton.galaxy.atoms import Atom
from skeleton.galaxy.brains import CompilerBrain, DistillerBrain, DreamBrain, EditorBrain, MemoryBrain
from skeleton.galaxy.codec import KnowledgeCodec
from skeleton.galaxy.decoder import KnowledgeDecoder
from skeleton.galaxy.hoag import galaxy_card
from skeleton.galaxy.librarians import LibrarianMesh
from skeleton.galaxy.mirrors import bind_mouth, mouth_mirrors


class GalaxySystem:
    def __init__(self) -> None:
        self.mesh = LibrarianMesh()
        self.codec = KnowledgeCodec()
        self.decoder = KnowledgeDecoder()
        self.memory = MemoryBrain(self.mesh, self.codec)
        self.compiler = CompilerBrain(self.mesh, self.codec)
        self.dream = DreamBrain(self.mesh, self.codec)
        self.distiller = DistillerBrain(self.mesh, self.codec)
        self.editor = EditorBrain(self.mesh, self.codec)
        self.pulses = 0

    def pulse(self, stimulus: str, *, citation: str = "", url: str = "", sleep: bool = False) -> Dict[str, Any]:
        dest = self.editor.route(stimulus)
        mem = self.memory.ingest(stimulus, citation=citation, url=url)
        compiled = self.compiler.compile(stimulus, source=mem, citation=citation)
        principle = None
        if dest in {"distiller", "editor"} or "like" in stimulus.lower() or "law" in stimulus.lower():
            principle = self.distiller.glean(stimulus, citation=citation)
        indexed = self.editor.index_topic(compiled)
        dream_card = self.dream.sleep() if sleep else None
        decoded = self.decoder.decode(stimulus, self.mesh.broadcast_search(stimulus, k=4), k=4)
        self.pulses += 1
        return {
            "kind": "galaxy-pulse",
            "pulses": self.pulses,
            "route": dest,
            "memory": mem.to_dict(),
            "compiled": compiled.to_dict(),
            "principle": principle.to_dict() if principle else None,
            "index": indexed.to_dict(),
            "dream": dream_card,
            "decoded": decoded,
            "wiki": self.mesh.wiki.catalog(),
            "librarians": self.mesh.to_dict(),
            "hoag": galaxy_card(),
            "stored_prose": 0,
        }

    def ingest_turns(self, turns: Iterable[str], *, citation: str = "") -> Dict[str, Any]:
        atoms = self.codec.encode_conversation(turns, citation=citation)
        for a in atoms:
            self.mesh.publish(a)
            if a.kind in {"commitment", "episode"}:
                self.editor.index_topic(a)
        structure = self.codec.structure_longform(atoms)
        density = self.codec.density(atoms)
        return {
            "kind": "longform",
            "atoms": len(atoms),
            "structure": structure,
            "density": density,
            "stored_prose": 0,
        }

    def snapshot(self) -> Dict[str, Any]:
        return {
            "kind": "galaxy",
            "pulses": self.pulses,
            "hoag": galaxy_card(),
            "mirrors": mouth_mirrors(),
            "librarians": self.mesh.to_dict(),
            "rules": self.distiller.rulebook(),
            "dreams": len(self.dream.dreams),
            "index": self.editor.refresh(),
            "stored_prose": 0,
        }

    def bind(self, family_id: str) -> Dict[str, Any]:
        return bind_mouth(family_id)


_LIVE: Optional[GalaxySystem] = None


def live_galaxy() -> GalaxySystem:
    global _LIVE
    if _LIVE is None:
        _LIVE = GalaxySystem()
    return _LIVE


def reset_galaxy() -> None:
    global _LIVE
    _LIVE = None
