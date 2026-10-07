#!/usr/bin/env python3
"""Benchmark frontier MemoryContract implementations without external services.

This is evidence tooling, not a latency gate. It compares the dependency-free
reference store with the persistent SQLite collection backend using identical
MemoryContract operations. Provider backends can be added later and must run
the same workload before promotion.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
import time
from pathlib import Path
from typing import Any

from skeleton.frontier.memory import InMemoryStore
from skeleton.frontier.memory_adapters import CollectionMemoryAdapter, SQLiteCollection


async def _benchmark_store(
    label: str,
    store: Any,
    *,
    items: int,
    queries: int,
    limit: int,
) -> dict[str, Any]:
    write_started = time.perf_counter_ns()
    for index in range(items):
        domain = "learning" if index % 2 == 0 else "game"
        await store.put(
            {
                "id": f"item-{index}",
                "text": f"frontier {domain} memory item {index}",
                "domain": domain,
                "metadata": {"bucket": index % 8},
            }
        )
    write_elapsed = time.perf_counter_ns() - write_started

    hits = 0
    search_started = time.perf_counter_ns()
    for index in range(queries):
        domain = "learning" if index % 2 == 0 else "game"
        result = await store.search(
            "frontier",
            limit=limit,
            filters={"domain": domain},
        )
        hits += len(result)
    search_elapsed = time.perf_counter_ns() - search_started

    return {
        "backend": label,
        "items": items,
        "queries": queries,
        "limit": limit,
        "hits": hits,
        "write_seconds": write_elapsed / 1_000_000_000,
        "search_seconds": search_elapsed / 1_000_000_000,
        "write_ops_per_second": (
            items / (write_elapsed / 1_000_000_000) if write_elapsed else None
        ),
        "search_ops_per_second": (
            queries / (search_elapsed / 1_000_000_000) if search_elapsed else None
        ),
    }


async def run_benchmark(
    *,
    items: int,
    queries: int,
    limit: int,
) -> dict[str, Any]:
    if items < 1 or queries < 1 or limit < 1:
        raise ValueError("items, queries and limit must all be positive")

    reference = await _benchmark_store(
        "in-memory-reference",
        InMemoryStore(),
        items=items,
        queries=queries,
        limit=limit,
    )

    with tempfile.TemporaryDirectory(prefix="frontier-memory-") as directory:
        collection = SQLiteCollection(Path(directory) / "benchmark.sqlite3")
        try:
            sqlite = await _benchmark_store(
                "sqlite-collection",
                CollectionMemoryAdapter(collection),
                items=items,
                queries=queries,
                limit=limit,
            )
            sqlite["persisted_items"] = collection.count()
        finally:
            collection.close()

    return {
        "workload": "frontier-memory-contract-v1",
        "source_semantics": {
            "repository": "Apeloff1/Prood",
            "path": "backend/services/rag_service.py",
            "blob": "b67167f1135744e74827ce03b0bf5d766e800cf4",
            "equivalent_repository": "Apeloff1/Tutolage",
        },
        "results": [reference, sqlite],
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--items", type=int, default=1000)
    parser.add_argument("--queries", type=int, default=200)
    parser.add_argument("--limit", type=int, default=10)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = asyncio.run(
        run_benchmark(
            items=args.items,
            queries=args.queries,
            limit=args.limit,
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
