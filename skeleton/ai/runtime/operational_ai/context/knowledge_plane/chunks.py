"""Deterministic source chunking; exact character coordinates and overlaps."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from .contracts import KnowledgeError, KnowledgePolicy


@dataclass(frozen=True, slots=True)
class Chunk:
    index: int
    start: int
    end: int
    passage: str
    digest: str


def split(text: str, policy: KnowledgePolicy) -> tuple[Chunk, ...]:
    if not isinstance(text, str) or not text:
        raise KnowledgeError('nonempty decoded document required')
    span, overlap = policy.chunk_characters, policy.chunk_overlap
    cursor, chunks = 0, []
    while cursor < len(text):
        if len(chunks) >= policy.max_chunks:
            raise KnowledgeError('source would exceed maximum chunk count')
        end = min(cursor + span, len(text))
        if end < len(text):
            candidate = text.rfind('\n', cursor + span // 2, end)
            if candidate > cursor + overlap and candidate > cursor + span // 2:
                end = candidate + 1
        part = text[cursor:end]
        if not part:
            raise KnowledgeError('chunker made no progress')
        chunks.append(Chunk(len(chunks), cursor, end, part,
                            sha256(part.encode('utf8')).hexdigest()))
        if end == len(text): break
        next_cursor = max(cursor + 1, end - overlap)
        if next_cursor >= end:
            raise KnowledgeError('invalid overlap progression')
        cursor = next_cursor
    if not chunks or chunks[0].start != 0 or chunks[-1].end != len(text):
        raise KnowledgeError('document chunk coverage incomplete')
    for a, b in zip(chunks, chunks[1:]):
        if not a.start < b.start <= a.end:
            raise KnowledgeError('document chunk coverage gap')
        if b.end <= a.end:
            raise KnowledgeError('nonmonotonic chunk end')
    return tuple(chunks)
