"""NPC quality integration tests."""
from __future__ import annotations

from skeleton.kernel.events import EventBus
from skeleton.pipelines.npc import NpcPipeline


def test_npc_pipeline_attaches_quality_contract():
    pipe = NpcPipeline(bus=EventBus())
    spec = pipe.run("stoic guardian who counts doorways", name="Gatewatch")
    payload = spec.to_dict()
    assert payload["quality"]["accepted"] is True
    assert payload["quality"]["quality"]["metadata"]["pipeline"] == "npc"
    assert payload["quality_stats"]["runs"] == 1
