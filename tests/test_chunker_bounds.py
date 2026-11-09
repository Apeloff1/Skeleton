"""Chunk windows must not skip text or accept a negative overlap."""

import pytest

from skeleton.kernel.errors import RetrievalError
from skeleton.retrieval.chunking import Chunker


def test_negative_overlap_is_rejected() -> None:
    with pytest.raises(RetrievalError):
        Chunker(window=32, overlap=-1)


def test_sliding_window_covers_the_document_without_gaps() -> None:
    text = "abcdefghijklmnopqrstuvwxyz"
    chunks = Chunker(window=10, overlap=4).chunk("doc", text)
    covered = bytearray(len(text))
    for chunk in chunks:
        assert text[chunk.start:chunk.end] == chunk.text
        for index in range(chunk.start, chunk.end):
            covered[index] = 1
    assert all(covered)
    assert chunks[0].chunk_id == "doc#0"
    assert chunks[-1].end == len(text)
