"""Corpus ingestion for retrieval — documents → chunks for the index.

The index accepts chunk-ified docs; ingestion stamps chunk ids and
returns them so a QueryPlanner can wire "corpus → chunks → index".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from skeleton.kernel.errors import RetrievalError
from skeleton.retrieval.chunking import Chunk, Chunker


@dataclass(frozen=True)
class Document:
    doc_id: str
    title: str
    body: str


class CorpusIngestor:
    """Convert documents to chunks; callers feed into InvertedIndex.add()."""

    def __init__(self, chunker: Chunker) -> None:
        self._chunker = chunker

    def ingest(self, document: Document) -> Tuple[Chunk, ...]:
        chunks = self._chunker.chunk(document.doc_id, document.body)
        if not chunks:
            raise RetrievalError("document produced no chunks", context={"doc": document.doc_id})
        return chunks

    def ingest_many(self, documents: Tuple[Document, ...]) -> Tuple[Chunk, ...]:
        out: List[Chunk] = []
        for document in documents:
            out.extend(self.ingest(document))
        return tuple(out)
