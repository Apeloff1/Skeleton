"""Dream themes index episodes. They do not copy episode bodies into RAG."""

import pytest

from skeleton.foundation.journal import EventJournal, JournaledBus
from skeleton.intelligence.dream import DreamEngine
from skeleton.kernel.events import EventBus
from skeleton.memory.consolidation import ConsolidationCycle
from skeleton.memory.mag import MAGStore
from skeleton.memory.rag import InMemoryTFIDFStore


def test_dream_indexes_a_cluster_without_copying_episode_text() -> None:
    mag = MAGStore("user-a")
    secret = "account token supersecretvalue"
    mag.add_episode(secret, tags={"voyage"})
    mag.add_episode("second voyage note", tags={"voyage"})
    mag.add_episode("unrelated", tags={"solo"})
    rag = InMemoryTFIDFStore()
    engine = DreamEngine(mag, rag)
    themes = engine.dream()
    assert [theme["tag"] for theme in themes] == ["voyage"]
    assert themes[0]["episodes"] == 2
    stored = next(iter(rag._chunks.values()))
    assert secret not in stored.text
    assert "supersecretvalue" not in stored.text
    assert stored.metadata["episode_ids"] == themes[0]["episode_ids"]
    again = engine.dream()
    assert again == themes
    assert len(rag._chunks) == 1


def test_a_dissolved_cluster_is_removed_from_retrieval() -> None:
    mag = MAGStore("user-a")
    first = mag.add_episode("alpha voyage", tags={"voyage"})
    mag.add_episode("beta voyage", tags={"voyage"})
    rag = InMemoryTFIDFStore()
    engine = DreamEngine(mag, rag)
    engine.dream()
    assert mag.delete(first) is True
    assert engine.dream() == []
    assert rag._chunks == {}


def test_dream_accepts_journaled_bus_used_by_genesis() -> None:
    mag = MAGStore("user-a")
    mag.add_episode("alpha voyage", tags={"voyage"})
    mag.add_episode("beta voyage", tags={"voyage"})
    rag = InMemoryTFIDFStore()
    journal = EventJournal()
    bus = JournaledBus(EventBus(), journal)
    engine = DreamEngine(mag, rag, bus=bus)

    themes = engine.dream()

    assert [theme["tag"] for theme in themes] == ["voyage"]
    assert len(journal) == 1
    entry = journal.entry(0)
    assert entry is not None
    assert entry.topic == "memory.dream.cycle"
    assert entry.payload["themes"] == 1


def test_dream_bounds_are_rejected() -> None:
    engine = DreamEngine(MAGStore("user-a"), InMemoryTFIDFStore())
    with pytest.raises(ValueError):
        engine.dream(min_cluster=1)
    with pytest.raises(ValueError):
        engine.recent_dreams(-1)


def test_consolidation_does_not_hide_a_dream_failure() -> None:
    class Krem:
        def due(self):
            return ["concept"]

        def retention(self, concept):
            return 0.5

        def observe(self, concept):
            return None

    class Scheduler:
        def schedule(self, item, interval_hours):
            return None

        def due_items(self):
            return []

    class BrokenDream:
        def dream(self, min_cluster=2):
            raise RuntimeError("dream failed")

    cycle = ConsolidationCycle(Krem(), Scheduler(), dream=BrokenDream())
    with pytest.raises(RuntimeError, match="dream failed"):
        cycle.cycle()
    with pytest.raises(ValueError):
        cycle.cycle(max_concepts=-1)
