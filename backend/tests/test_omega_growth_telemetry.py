"""Preserve the historical IQ event stream without unbounded tasks."""
import asyncio
from gameforge.omega.integration import OmegaFabric
from gameforge import prood


def test_growth_telemetry_preserves_event_contract(monkeypatch):
    async def scenario():
        fabric = OmegaFabric()
        monkeypatch.setattr(fabric, "_persist_enabled", lambda: False)
        events = []
        async def publish(event_type, payload):
            events.append((event_type, payload))
            return {"persistence": "journaled"}
        monkeypatch.setattr(prood.event_bus, "publish", publish)
        fabric._grow("agent_emit", "worker")
        fabric._grow("jeeves_emit", "jeeves")
        await fabric._growth_task
        assert [e[0] for e in events] == ["iq.grow", "iq.grow"]
        assert [e[1]["iq"] for e in events] == [101.0, 102.0]
        assert all(e[1]["basis"] == "heuristic_emission_counter" for e in events)
        assert fabric._growth_queue.empty()
    asyncio.run(scenario())
