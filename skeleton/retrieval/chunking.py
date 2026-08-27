"""Retrieval chunking — fixed windows with overlap for index ingestion.

Before a document reaches the InvertedIndex it must be split. The chunker
produces stable chunk ids (doc_id#n) with character offsets so results
can point back into the source.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from skeleton.kernel.errors import RetrievalError


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    text: str
    start: int
    end: int


class Chunker:
    """Sliding-window splitter with overlap."""

    def __init__(self, *, window: int = 512, overlap: int = 64) -> None:
        if window <= 0:
            raise RetrievalError("window must be positive")
        if overlap >= window:
            raise RetrievalError("overlap must be smaller than window")
        self.window = window
        self.overlap = overlap

    def chunk(self, doc_id: str, text: str) -> Tuple[Chunk, ...]:
        if not text:
            return tuple()
        step = self.window - self.overlap
        out: List[Chunk] = []
        index = 0
        position = 0
        while position < len(text):
            end = min(position + self.window, len(text))
            out.append(
                Chunk(
                    chunk_id=f"{doc_id}#{index}",
                    doc_id=doc_id,
                    text=text[position:end],
                    start=position,
                    end=end,
                )
            )
            index += 1
            position += step
        return tuple(out)
