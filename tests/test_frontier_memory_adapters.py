"""Contract evidence for the promoted Prood RAG memory adapter."""

from __future__ import annotations

import asyncio
import unittest

from skeleton.frontier.memory_adapters import CollectionMemoryAdapter


class _FakeCollection:
    def __init__(self) -> None:
        self.added: list[dict[str, object]] = []
        self.deleted: list[str] = []
        self.queries: list[dict[str, object]] = []

    def add(self, *, documents, metadatas, ids) -> None:
        self.added.append(
            {"documents": documents, "metadatas": metadatas, "ids": ids}
        )

    def query(self, *, query_texts, n_results, where=None):
        self.queries.append(
            {"query_texts": query_texts, "n_results": n_results, "where": where}
        )
        return {
            "documents": [["alpha memory"]],
            "metadatas": [[{"topic": "alpha"}]],
            "ids": [["m1"]],
            "distances": [[0.25]],
        }

    def delete(self, *, ids) -> None:
        self.deleted.extend(ids)


class CollectionMemoryAdapterTests(unittest.TestCase):
    def test_collection_semantics_are_preserved_behind_memory_contract(self) -> None:
        collection = _FakeCollection()
        adapter = CollectionMemoryAdapter(collection)

        async def scenario() -> None:
            memory_id = await adapter.put(
                {
                    "id": "m1",
                    "content": "alpha memory",
                    "metadata": {"topic": "alpha"},
                }
            )
            self.assertEqual(memory_id, "m1")

            hits = await adapter.search(
                "alpha",
                limit=2,
                filters={"topic": "alpha"},
            )
            self.assertEqual(
                hits,
                [
                    {
                        "content": "alpha memory",
                        "id": "m1",
                        "metadata": {"topic": "alpha"},
                        "relevance": 0.75,
                    }
                ],
            )

            await adapter.delete("m1")

        asyncio.run(scenario())

        self.assertEqual(
            collection.added,
            [
                {
                    "documents": ["alpha memory"],
                    "metadatas": [{"topic": "alpha"}],
                    "ids": ["m1"],
                }
            ],
        )
        self.assertEqual(
            collection.queries,
            [
                {
                    "query_texts": ["alpha"],
                    "n_results": 2,
                    "where": {"topic": "alpha"},
                }
            ],
        )
        self.assertEqual(collection.deleted, ["m1"])


if __name__ == "__main__":
    unittest.main()
