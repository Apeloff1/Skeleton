"""Retrieval sink, video observations, and hybrid rank. No empty returns."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9:/._-]+", text.lower())


def _vec(text: str, dim: int = 16) -> list[float]:
    buckets = [0.0] * dim
    for token in _tokens(text):
        digest = hashlib.sha256(token.encode()).digest()
        buckets[digest[0] % dim] += 1.0
        buckets[digest[1] % dim] += 0.5
    norm = math.sqrt(sum(x * x for x in buckets)) or 1.0
    return [x / norm for x in buckets]


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


@dataclass
class IngestRecord:
    content_hash: str
    body: str
    metadata: dict


class MemoryRetrievalSink:
    def __init__(self) -> None:
        self.rows: dict[str, IngestRecord] = {}

    def upsert(self, record: dict) -> None:
        digest = str(record.get("content_hash") or record.get("id") or "")
        if not digest:
            raise ValueError("upsert requires content_hash")
        self.rows[digest] = IngestRecord(digest, str(record.get("body", "")), dict(record.get("metadata") or {}))


@dataclass
class VideoFrame:
    start_ms: int
    end_ms: int
    modality: str
    description: str
    confidence: float
    origin_id: str


class TranscriptVideoAdapter:
    def __init__(self, lines: list[str]) -> None:
        self.lines = lines

    def observations(self, source_url: str):
        for index, line in enumerate(self.lines):
            yield VideoFrame(index * 1000, index * 1000 + 900, "transcript", line, 0.9, f"{source_url}#{index}")


class HybridRank:
    def __init__(self, documents: list[dict], edges: list[tuple[str, str]]) -> None:
        self.documents = documents
        self.edges = edges
        self.vectors = {doc["id"]: _vec(doc.get("text", "")) for doc in documents}

    def keyword(self, query: str, room_id: str) -> list[dict]:
        terms = set(_tokens(query))
        hits = []
        for doc in self.documents:
            if room_id and doc.get("room") not in {room_id, "*"}:
                continue
            overlap = terms.intersection(_tokens(doc.get("text", "")))
            if overlap:
                hits.append({"id": doc["id"], "lane": "keyword", "score": len(overlap)})
        return hits

    def vector(self, query: str, room_id: str) -> list[dict]:
        q = _vec(query)
        hits = []
        for doc in self.documents:
            if room_id and doc.get("room") not in {room_id, "*"}:
                continue
            score = _cosine(q, self.vectors[doc["id"]])
            if score > 0:
                hits.append({"id": doc["id"], "lane": "vector", "score": score})
        return hits

    def graph(self, query: str, room_id: str) -> list[dict]:
        seeds = {doc["id"] for doc in self.documents if room_id in doc.get("text", "") or room_id == doc.get("room")}
        hits = []
        for left, right in self.edges:
            if left in seeds or right in seeds:
                hits.append({"id": right if left in seeds else left, "lane": "graph", "score": 1.0})
        return hits

    def retrieve(self, query: str, room_id: str, top_k: int = 10) -> list[dict]:
        pooled: dict[str, dict] = {}
        for row in self.keyword(query, room_id) + self.vector(query, room_id) + self.graph(query, room_id):
            current = pooled.setdefault(row["id"], {"id": row["id"], "score": 0.0, "lanes": []})
            current["score"] += float(row["score"])
            current["lanes"].append(row["lane"])
        ranked = sorted(pooled.values(), key=lambda item: item["score"], reverse=True)
        return ranked[:top_k]
