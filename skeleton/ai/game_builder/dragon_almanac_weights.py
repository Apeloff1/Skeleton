"""Compact sparse retrieval weights over canonical reviewed notes.

These are deterministic lexical routing weights, NOT trained neural weights.
The source root is revalidated on every retrieval. Source rights, Wiki/HOAG
memory approval and training authorization are never inferred from a pack.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from hashlib import sha256
import json
import re
import zlib

from .contracts import canonical_json
from .dragon_almanacs import _auth
from .reviewed_knowledge import ReviewedKnowledgeStore, _integer, _text

WORD = re.compile(r"[^\W_]+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class AlmanacWeightPack:
    owner: str
    knowledge_root: str
    payload: bytes
    payload_digest: str
    raw_bytes: int
    documents: int


def build_weight_pack(library: ReviewedKnowledgeStore, owner: str, *, authorized: bool,
                      max_notes: int = 10_000) -> AlmanacWeightPack:
    _auth(owner, authorized)
    _integer(max_notes, "note budget", 1, 10_000)
    documents = []
    index = defaultdict(list)
    stances = defaultdict(set)
    rows = library._rows(owner)
    root = library.snapshot_root(owner, authorized=True)
    for source in rows:
        if source["status"] != "active" or "design_reference" not in source["allowed_scopes"]:
            continue
        for entry in source["notes"]:
            note = entry["note"]
            if len(documents) >= max_notes:
                raise ValueError("pack exceeds note budget; shard by scope first")
            number = len(documents)
            documents.append({"source_id": source["source_id"], "revision": source["revision_digest"],
                "source_url": source["source_url"], "note_id": note["note_id"],
                "mechanic": note["mechanic"], "statement": note["statement"],
                "stance": note["stance"], "dependence_group": note["dependence_group"],
                "confidence_ppm": note["confidence_ppm"], "span": [note["start"], note["end"]]})
            stances[note["mechanic"]].add(note["stance"])
            weights = Counter(WORD.findall(note["statement"].casefold()))
            for term in WORD.findall(note["mechanic"].casefold()):
                weights[term] += 6
            for term, weight in sorted(weights.items()):
                index[term].append([number, min(255, weight)])
    body = {"schema": "skeleton.dragon.almanac_sparse_weights.v1", "owner": owner,
            "knowledge_root": root, "documents": documents, "postings": dict(index),
            "conflicting_mechanics": sorted(k for k, v in stances.items() if "challenges" in v),
            "weight_semantics": "bounded_integer_lexical_frequency_not_neural_parameters",
            "training_authorized": False, "release_authorized": False}
    raw = canonical_json(body).encode()
    if len(raw) > 32_000_000:
        raise ValueError("uncompressed pack budget exceeded")
    payload = zlib.compress(raw, level=9)
    if library.snapshot_root(owner, authorized=True) != root:
        raise ValueError("knowledge changed while compiling pack")
    return AlmanacWeightPack(owner, root, payload, sha256(payload).hexdigest(), len(raw), len(documents))


def retrieve_weight_pack(pack: AlmanacWeightPack, library: ReviewedKnowledgeStore,
                         owner: str, query: str, *, authorized: bool, limit: int = 12) -> dict:
    _auth(owner, authorized)
    _text(query, "query", 300); _integer(limit, "result limit", 1, 100)
    if not isinstance(pack, AlmanacWeightPack) or pack.owner != owner:
        raise ValueError("owner-bound weight pack required")
    if (not isinstance(pack.payload, bytes) or len(pack.payload) > 32_000_000
            or sha256(pack.payload).hexdigest() != pack.payload_digest):
        raise ValueError("pack integrity invalid")
    if library.snapshot_root(owner, authorized=True) != pack.knowledge_root:
        raise ValueError("stale pack: rebuild from current canonical evidence")
    decoder = zlib.decompressobj()
    raw = decoder.decompress(pack.payload, 32_000_001)
    if len(raw) > 32_000_000 or not decoder.eof or decoder.unused_data or len(raw) != pack.raw_bytes:
        raise ValueError("pack size or compression stream invalid")
    body = json.loads(raw)
    if body["owner"] != owner or body["knowledge_root"] != pack.knowledge_root:
        raise ValueError("pack provenance mismatch")
    scores = Counter()
    for term in sorted(set(WORD.findall(query.casefold()))):
        for number, weight in body["postings"].get(term, ()):
            scores[number] += weight
    selected = sorted(scores, key=lambda n: (-scores[n], n))[:limit]
    hits = [{**body["documents"][n], "routing_weight": scores[n]} for n in selected]
    conflicts = sorted({h["mechanic"] for h in hits} & set(body["conflicting_mechanics"]))
    # A mutable local pack is not an authentication boundary. Verify selected
    # statements against the canonical notes; a recomputed hash grants nothing.
    canonical_rows = library._rows(owner)
    source_urls = {r["source_id"]: r["source_url"] for r in canonical_rows}
    notes = {(r["source_id"], r["revision_digest"], e["note"]["note_id"]): e["note"]
             for r in canonical_rows if r["status"] == "active" and "design_reference" in r["allowed_scopes"]
             for e in r["notes"]}
    for hit in hits:
        note = notes.get((hit["source_id"], hit["revision"], hit["note_id"]))
        if note is None or any(hit[k] != note[k] for k in ("statement", "mechanic", "stance", "dependence_group", "confidence_ppm")):
            raise ValueError("pack differs from canonical reviewed notes")
        if hit["source_url"] != source_urls[hit["source_id"]] or hit["span"] != [note["start"], note["end"]]:
            raise ValueError("pack citation differs from canonical evidence")
    actual_conflicts = {note["mechanic"] for note in notes.values() if note["stance"] == "challenges"}
    conflicts = sorted({h["mechanic"] for h in hits} & actual_conflicts)
    return {"hits": hits, "conflicting_mechanics": conflicts, "knowledge_root": pack.knowledge_root,
            "pack_digest": pack.payload_digest, "neural_weights": False,
            "memory_promotion_authorized": False, "training_authorized": False,
            "release_authorized": False, "requires_review": True}
