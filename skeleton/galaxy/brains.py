"""Five brains of the internal knowledge organism.

1 Memory     — capture / episodic working buffer
2 Compiler   — second-brain compiler (CODE×PARA×Zettel → mirror galaxy)
3 Dream      — stores dreams; offline consolidation + replay
4 Distiller  — principles gleaned; bake rules, collapse contradictions
5 Editor     — traffic control + master index + freshness / supersession

Each brain writes only house dialect. Contact with a teacher still
obeys LoRA+SGD+Hebb+absorb at the cortex layer; brains store the
resulting commitments, not teacher weights.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from skeleton.galaxy.atoms import Atom, house_dialect, token_set
from skeleton.galaxy.codec import KnowledgeCodec
from skeleton.galaxy.hoag import color_of
from skeleton.galaxy.librarians import LibrarianMesh


class MemoryBrain:
    """Brain 1 — agentic memory with obscure steps.

    Steps (deep cut):
      sense → tokenise → salience → write-route (skip|new|update)
      → flash-shelf → session-bind → provenance → wiki-report
    Dual-layer write: fast route now, slow consolidate later (dream).
    """

    name = "memory"

    def __init__(self, mesh: LibrarianMesh, codec: KnowledgeCodec) -> None:
        self.mesh = mesh
        self.codec = codec
        self.routes: List[str] = []

    def ingest(self, stimulus: str, *, citation: str = "", url: str = "") -> Atom:
        toks = token_set(stimulus)
        if len(toks) < 2:
            self.routes.append("skip")
            atom = self.codec.encode(stimulus or "silence", kind="capture", brain=self.name)
            atom.confidence = 0.2
            return self.mesh.publish(atom)
        existing = self.mesh.of(self.name).search(stimulus, k=1)
        if existing and existing[0].tokens == toks:
            self.routes.append("update")
            prev = existing[0]
            prev.confidence = min(0.99, prev.confidence + 0.04)
            prev.ts = time.time()
            self.mesh.wiki.hear(self.mesh.of(self.name), prev)
            return prev
        self.routes.append("new")
        atom = self.codec.encode(stimulus, kind="capture", brain=self.name, citation=citation, url=url)
        return self.mesh.publish(atom)


class CompilerBrain:
    """Brain 2 — SOTA second-brain compiler → mirror galaxy.

    Capture atoms become zettels (one idea), filed by actionability:
      project | area | resource | archive
    Linked into the ring. This is the 2026 second-brain map taken
    deeper: hot-swap mouths sit on the same compiled graph.
    """

    name = "compiler"
    BUCKETS = ("project", "area", "resource", "archive")

    def __init__(self, mesh: LibrarianMesh, codec: KnowledgeCodec) -> None:
        self.mesh = mesh
        self.codec = codec

    def _bucket(self, stimulus: str) -> str:
        t = set(token_set(stimulus))
        if t & {"plan", "build", "ship", "deadline", "cut", "go"}:
            return "project"
        if t & {"law", "genos", "mouth", "era", "health"}:
            return "area"
        if t & {"like", "cite", "ref", "pointer", "elden", "stardew"}:
            return "resource"
        return "archive"

    def compile(self, stimulus: str, source: Optional[Atom] = None, *, citation: str = "") -> Atom:
        bucket = self._bucket(stimulus)
        atom = self.codec.encode(
            stimulus,
            kind="zettel",
            brain=self.name,
            citation=citation,
            depth_hint=3,
            tags=(bucket, "compiled"),
        )
        if source:
            atom.parent = source.id
            atom.links = (source.id,)
        return self.mesh.publish(atom)


class DreamBrain:
    """Brain 3 — stores dreams.

    Offline: replay high-confidence captures, prune low-salience,
    abstract tag clusters into episode atoms. Deterministic given seed.
    """

    name = "dream"

    def __init__(self, mesh: LibrarianMesh, codec: KnowledgeCodec) -> None:
        self.mesh = mesh
        self.codec = codec
        self.dreams: List[Atom] = []

    def sleep(self, *, replay_k: int = 6, prune_floor: float = 0.25) -> Dict[str, Any]:
        shelf = self.mesh.of("memory").all()
        ranked = sorted(shelf, key=lambda a: a.confidence, reverse=True)
        replayed = ranked[:replay_k]
        pruned = 0
        for a in shelf:
            if a.confidence < prune_floor and a.kind == "capture":
                a.superseded_by = "dream-prune"
                pruned += 1
        tags: Dict[str, List[Atom]] = {}
        for a in replayed:
            for tag in a.tags or ("untagged",):
                tags.setdefault(tag, []).append(a)
        written = 0
        for tag, group in tags.items():
            if len(group) < 2:
                continue
            dialect = house_dialect(" ".join(g.topic for g in group))
            dream = self.codec.encode(
                dialect,
                kind="dream",
                brain=self.name,
                depth_hint=2,
                tags=(tag, "consolidated"),
            )
            dream.links = tuple(g.id for g in group[:8])
            self.mesh.publish(dream)
            self.dreams.append(dream)
            written += 1
        if not written and replayed:
            dream = self.codec.encode(
                " ".join(a.topic for a in replayed[:4]),
                kind="dream",
                brain=self.name,
                depth_hint=2,
                tags=("replay",),
            )
            self.mesh.publish(dream)
            self.dreams.append(dream)
            written = 1
        return {
            "replayed": len(replayed),
            "pruned": pruned,
            "dreams": written,
            "stored": len(self.dreams),
            "stored_prose": 0,
        }


class DistillerBrain:
    """Brain 4 — reasoning and principles gleaned.

    Distiller writes one rule, not one record. Editor may overwrite.
    Rulebook stays small: a principle earns its slot by killing a worse one.
    """

    name = "distiller"
    MAX_RULES = 31

    def __init__(self, mesh: LibrarianMesh, codec: KnowledgeCodec) -> None:
        self.mesh = mesh
        self.codec = codec
        self.rules: Dict[str, Atom] = {}

    def glean(self, stimulus: str, *, citation: str = "") -> Atom:
        toks = token_set(stimulus)
        head = " ".join(toks[:8]) or "observe"
        rule_text = f"rule:{head}"
        atom = self.codec.encode(
            rule_text,
            kind="principle",
            brain=self.name,
            citation=citation,
            depth_hint=4,
            tags=("rule",),
        )
        atom.confidence = 0.84
        # collapse near-duplicate
        for rid, prev in list(self.rules.items()):
            if set(prev.tokens) & set(atom.tokens) and len(set(prev.tokens) & set(atom.tokens)) >= 2:
                prev.superseded_by = atom.id
                atom.tags = tuple(set(atom.tags) | {"overwrite"})
                del self.rules[rid]
                break
        if len(self.rules) >= self.MAX_RULES:
            oldest = min(self.rules.values(), key=lambda a: a.confidence)
            oldest.superseded_by = atom.id
            self.rules.pop(oldest.id, None)
        self.rules[atom.id] = atom
        return self.mesh.publish(atom)

    def rulebook(self) -> List[Dict[str, Any]]:
        return [a.to_dict() for a in self.rules.values()]


class EditorBrain:
    """Brain 5 — traffic control + master index.

    Routes atoms to brains, keeps knowledge current, supersedes stale
    index entries, refuses conflicting principles (overwrite, do not fork).
    """

    name = "editor"

    def __init__(self, mesh: LibrarianMesh, codec: KnowledgeCodec) -> None:
        self.mesh = mesh
        self.codec = codec
        self.index: Dict[str, str] = {}
        self.traffic: List[str] = []

    def route(self, stimulus: str) -> str:
        t = set(token_set(stimulus))
        if t & {"dream", "sleep", "replay", "consolidate"}:
            dest = "dream"
        elif t & {"rule", "principle", "law", "glean"}:
            dest = "distiller"
        elif t & {"compile", "zettel", "para", "second"}:
            dest = "compiler"
        elif t & {"index", "fresh", "stale", "edit"}:
            dest = "editor"
        else:
            dest = "memory"
        self.traffic.append(dest)
        return dest

    def index_topic(self, atom: Atom) -> Atom:
        key = atom.topic
        prev_id = self.index.get(key)
        card = self.codec.encode(
            atom.topic,
            kind="index",
            brain=self.name,
            citation=atom.citation,
            url=atom.url,
            depth_hint=5,
            tags=("index", atom.brain),
        )
        card.links = (atom.id,)
        if prev_id:
            old = self.mesh.of(self.name).get(prev_id)
            if old:
                old.superseded_by = card.id
        self.index[key] = card.id
        return self.mesh.publish(card)

    def audit(self, principles: Optional[List[Atom]] = None) -> Dict[str, Any]:
        from skeleton.galaxy.mad import audit as mad_audit
        pool = principles
        if pool is None:
            pool = [a for a in self.mesh.of("distiller").all() if a.kind == "principle"]
        return mad_audit(pool)

    def refresh(self) -> Dict[str, Any]:
        stale = 0
        now = time.time()
        for lib in self.mesh.brains.values():
            for atom in lib.all():
                age = now - atom.ts
                if age > 86_400 and atom.kind in {"capture", "zettel"}:
                    atom.confidence = max(0.15, atom.confidence * 0.92)
                    stale += 1
        return {"index_size": len(self.index), "decayed": stale, "traffic": list(self.traffic[-16:]), "stored_prose": 0}
