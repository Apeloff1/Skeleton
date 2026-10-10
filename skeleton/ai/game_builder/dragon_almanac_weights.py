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


def _document(source: dict, note: dict) -> dict:
    """The sole canonical projection of a reviewed note into a routing pack."""
    return {
        "source_id": source["source_id"],
        "revision": source["revision_digest"],
        "source_url": source["source_url"],
        "note_id": note["note_id"],
        "mechanic": note["mechanic"],
        "statement": note["statement"],
        "stance": note["stance"],
        "dependence_group": note["dependence_group"],
        "confidence_ppm": note["confidence_ppm"],
        "span": [note["start"], note["end"]],
    }


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
            documents.append(_document(source, note))
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
    try:
        decoder = zlib.decompressobj()
        raw = decoder.decompress(pack.payload, 32_000_001)
    except zlib.error as exc:
        raise ValueError("pack compression stream invalid") from exc
    if len(raw) > 32_000_000 or not decoder.eof or decoder.unused_data or len(raw) != pack.raw_bytes:
        raise ValueError("pack size or compression stream invalid")
    try:
        body = json.loads(raw)
        # Requiring the exact canonical encoding rejects duplicate keys, non-finite
        # numeric tokens and alternate parses even if the pack hash is recomputed.
        if not isinstance(body, dict) or canonical_json(body).encode("utf-8") != raw:
            raise ValueError("weight pack is not canonical JSON")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise ValueError("weight pack JSON integrity invalid") from exc
    if (body.get("schema") != "skeleton.dragon.almanac_sparse_weights.v1"
            or body.get("owner") != owner
            or body.get("knowledge_root") != pack.knowledge_root
            or body.get("weight_semantics") != "bounded_integer_lexical_frequency_not_neural_parameters"
            or body.get("training_authorized") is not False
            or body.get("release_authorized") is not False):
        raise ValueError("pack schema or provenance mismatch")
    documents = body.get("documents")
    postings = body.get("postings")
    if (type(pack.documents) is not int or not 0 <= pack.documents <= 10_000
            or not isinstance(documents, list) or len(documents) != pack.documents
            or not isinstance(postings, dict)):
        raise ValueError("weight pack document index invalid")
    canonical_rows = library._rows(owner)
    expected_documents = [
        _document(source, entry["note"])
        for source in canonical_rows
        if source["status"] == "active" and "design_reference" in source["allowed_scopes"]
        for entry in source["notes"]
    ]
    if len(expected_documents) > 10_000 or documents != expected_documents:
        raise ValueError("weight pack document sequence differs from canonical reviewed evidence")
    query_terms = sorted(set(WORD.findall(query.casefold())))
    scores = Counter()
    for term in query_terms:
        entries = postings.get(term, [])
        if not isinstance(entries, list) or len(entries) > len(documents):
            raise ValueError("weight pack postings malformed")
        last_number = -1
        for entry in entries:
            if (not isinstance(entry, list) or len(entry) != 2
                    or type(entry[0]) is not int or type(entry[1]) is not int
                    or not last_number < entry[0] < len(documents)
                    or not 1 <= entry[1] <= 255):
                raise ValueError("weight pack postings invalid or out of order")
            last_number = entry[0]
            scores[entry[0]] += entry[1]
    selected = sorted(scores, key=lambda n: (-scores[n], n))[:limit]
    hits = [{**documents[n], "routing_weight": scores[n]} for n in selected]
    # A mutable local pack is not an authentication boundary. Verify selected
    # statements against the canonical notes; a recomputed hash grants nothing.
    source_urls = {r["source_id"]: r["source_url"] for r in canonical_rows}
    notes = {(r["source_id"], r["revision_digest"], e["note"]["note_id"]): e["note"]
             for r in canonical_rows if r["status"] == "active" and "design_reference" in r["allowed_scopes"]
             for e in r["notes"]}
    # A rehashed pack must not bias retrieval with invented weights or suppress
    # matching reviewed notes. Reconstruct only the requested term postings from
    # canonical evidence, not the unrelated vocabulary's full index.
    expected = {term: [] for term in query_terms}
    for number, entry in enumerate(documents):
        if not isinstance(entry, dict):
            raise ValueError("weight pack document malformed")
        key = (entry.get("source_id"), entry.get("revision"), entry.get("note_id"))
        note = notes.get(key)
        if (note is None
                or any(entry.get(k) != note[k] for k in (
                    "statement", "mechanic", "stance",
                    "dependence_group", "confidence_ppm",
                ))
                or entry.get("source_url") != source_urls.get(key[0])
                or entry.get("span") != [note["start"], note["end"]]):
            raise ValueError("weight pack document not canonical reviewed evidence")
        weights = Counter(WORD.findall(note["statement"].casefold()))
        for term in WORD.findall(note["mechanic"].casefold()):
            weights[term] += 6
        for term in query_terms:
            if weights.get(term, 0):
                expected[term].append([number, min(255, weights[term])])
    if any(postings.get(term, []) != expected[term] for term in query_terms):
        raise ValueError("weight pack postings differ from canonical reviewed notes")
    for hit in hits:
        note = notes.get((hit["source_id"], hit["revision"], hit["note_id"]))
        if note is None or any(hit[k] != note[k] for k in ("statement", "mechanic", "stance", "dependence_group", "confidence_ppm")):
            raise ValueError("pack differs from canonical reviewed notes")
        if hit["source_url"] != source_urls[hit["source_id"]] or hit["span"] != [note["start"], note["end"]]:
            raise ValueError("pack citation differs from canonical evidence")
    actual_conflicts = {note["mechanic"] for note in notes.values() if note["stance"] == "challenges"}
    conflicts = sorted({h["mechanic"] for h in hits} & actual_conflicts)
    if library.snapshot_root(owner, authorized=True) != pack.knowledge_root:
        raise ValueError("knowledge changed during weight-pack retrieval")
    return {"hits": hits, "conflicting_mechanics": conflicts, "knowledge_root": pack.knowledge_root,
            "pack_digest": pack.payload_digest, "neural_weights": False,
            "memory_promotion_authorized": False, "training_authorized": False,
            "release_authorized": False, "requires_review": True}
