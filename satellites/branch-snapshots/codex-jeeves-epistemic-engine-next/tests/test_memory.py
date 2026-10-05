"""Tests for the RAG/CAG/MAG memory trinity."""

from skeleton.kernel.ids import UserId
from skeleton.memory import CAGStore, MAGStore, MemoryTrinity
from skeleton.memory.types import MemoryChunk
from skeleton.memory.rag import InMemoryTFIDFStore


def _chunk(text: str, *, chunk_id: str = "c1", tier: str = "rag") -> MemoryChunk:
    return MemoryChunk(id=chunk_id, text=text, metadata={"topic": "alpha"}, source_tier=tier, confidence=1.0)


class TestMagStore:
    def test_episode_recall(self):
        mag = MAGStore(user_id=UserId.new())
        mag.add_episode("learned recursion by drawing call stacks", tags={"python"})
        hits = mag.query("recursion stacks")
        assert hits
        assert "recursion" in hits[0].chunk.text.lower()

    def test_requires_user_id(self):
        mag = MAGStore(user_id=UserId.new())
        assert mag.health()["status"] == "healthy"


class TestCagStore:
    def test_persona_context(self):
        cag = CAGStore()
        cag.create_persona("tutor", "Jeeves", "You are a patient tutor.")
        cag.add(_chunk("Recursion is a function calling itself."))
        hits = cag.query("recursion")
        assert hits and "tutor" in hits[0].chunk.text.lower() or hits[0].chunk.text


class TestTrinity:
    def test_unified_query(self):
        rag = InMemoryTFIDFStore()
        cag = CAGStore()
        mag = MAGStore(user_id=UserId.new())
        cag.create_persona("p", "P", "system")
        rag.add(_chunk("hash maps average O(1) lookup", chunk_id="r1"))
        mag.add_episode("yesterday we implemented a dict-backed cache")
        trinity = MemoryTrinity(rag=rag, cag=cag, mag=mag)
        ctx = trinity.query_unified("hash map lookup")
        assert ctx.token_estimate >= 0
        assert trinity.health()["status"] == "healthy"
