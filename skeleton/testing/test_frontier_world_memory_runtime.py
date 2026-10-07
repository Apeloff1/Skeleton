from __future__ import annotations

from datetime import datetime, timezone

import pytest

from skeleton.frontier.agent_runtime import AgentRuntime
from skeleton.frontier.events import DomainEvent, EventBus, SQLiteEventJournal
from skeleton.frontier.memory_adapters import CollectionMemoryAdapter, SQLiteCollection
from skeleton.frontier.world import calculate_route, project_fog_of_war, region_from_record


class WorldMemoryIntegrator:
    name = "world-memory-integrator"
    capabilities = {"world.route", "world.explore", "memory.search"}

    async def run(self, task, context=None):
        context = dict(context or {})
        return {
            "task": task,
            "route_distance": context["route"]["distance"],
            "exploration_percentage": context["fog"]["exploration_percentage"],
            "memory_ids": [hit["id"] for hit in context["memory_hits"]],
        }


def _source_region():
    return region_from_record(
        {
            "id": "barnacle_bay",
            "name": "Barnacle Bay",
            "difficulty": 1,
            "theme": "coastal",
            "bounds": {"x": 0, "y": 0, "width": 1000, "height": 800},
            "dangers": [],
            "points_of_interest": [
                {
                    "id": "starting_dock",
                    "name": "Starting Dock",
                    "type": "port",
                    "x": 100,
                    "y": 400,
                },
                {
                    "id": "lighthouse_point",
                    "name": "Lighthouse Point",
                    "type": "landmark",
                    "x": 800,
                    "y": 200,
                },
            ],
        }
    )


@pytest.mark.asyncio
async def test_world_policy_persists_executes_and_emits_durable_event(tmp_path):
    region = _source_region()
    route = calculate_route((100, 400), (800, 200), [region])
    fog = project_fog_of_war([region], ["starting_dock"])

    collection = SQLiteCollection(tmp_path / "frontier-world.sqlite3", namespace="world")
    journal = SQLiteEventJournal(
        tmp_path / "frontier-events.sqlite3",
        namespace="world-runtime",
    )
    memory = CollectionMemoryAdapter(collection)
    try:
        await memory.put(
            {
                "id": "route:barnacle-bay",
                "content": "Barnacle Bay route from Starting Dock to Lighthouse Point",
                "domain": "world",
                "region_id": region.id,
                "metadata": {
                    "distance": route["distance"],
                    "exploration_percentage": fog["exploration_percentage"],
                },
            }
        )
        hits = await memory.search(
            "Barnacle Bay route",
            filters={"domain": "world", "region_id": "barnacle_bay"},
        )

        runtime = AgentRuntime()
        runtime.register(WorldMemoryIntegrator())
        execution_args = {
            "context": {"route": route, "fog": fog, "memory_hits": hits},
            "required_capabilities": {
                "world.route",
                "world.explore",
                "memory.search",
            },
            "source_repository": "Apeloff1/Lorebuffa",
            "source_revision": "a32259d514710c3e87d7ce5fe42f6fb73e63ca1b",
            "source_path": "backend/world_map.py",
            "idempotency_key": "world:barnacle_bay:starting_dock:lighthouse_point",
        }
        result = await runtime.execute(
            "world-memory-integrator",
            "summarize promoted world state",
            **execution_args,
        )

        assert result.succeeded
        assert result.output == {
            "task": "summarize promoted world state",
            "route_distance": pytest.approx(728.01),
            "exploration_percentage": 50.0,
            "memory_ids": ["route:barnacle-bay"],
        }
        assert result.provenance is not None
        assert result.provenance.source_repository == "Apeloff1/Lorebuffa"
        assert result.provenance.source_revision == (
            "a32259d514710c3e87d7ce5fe42f6fb73e63ca1b"
        )
        assert result.provenance.source_path == "backend/world_map.py"
        assert result.provenance.metadata["required_capabilities"] == [
            "memory.search",
            "world.explore",
            "world.route",
        ]
        assert "idempotency_key_sha256" in result.provenance.metadata

        repeated = await runtime.execute(
            "world-memory-integrator",
            "summarize promoted world state",
            **execution_args,
        )
        assert repeated is result

        bus = EventBus(journal=journal)
        emitted = []

        async def capture(event):
            emitted.append((event.topic, dict(event.payload)))

        await bus.subscribe("world.summary.completed", capture)
        delivered = await bus.publish(
            DomainEvent.create(
                "world.summary.completed",
                {
                    "region_id": region.id,
                    "route_distance": result.output["route_distance"],
                    "exploration_percentage": result.output[
                        "exploration_percentage"
                    ],
                    "memory_ids": result.output["memory_ids"],
                },
            )
        )

        assert delivered == 1
        assert emitted == [
            (
                "world.summary.completed",
                {
                    "region_id": "barnacle_bay",
                    "route_distance": 728.01,
                    "exploration_percentage": 50.0,
                    "memory_ids": ["route:barnacle-bay"],
                },
            )
        ]
        assert await journal.pending_count() == 0
    finally:
        collection.close()
        journal.close()


def test_world_source_clock_fixture_is_explicit():
    fixture_time = datetime(2026, 9, 15, 9, 45, tzinfo=timezone.utc)
    assert fixture_time.isoformat() == "2026-09-15T09:45:00+00:00"
