from skeleton.kernel.events import DomainEvent, EventBus
from skeleton.pipelines.game_logic import GameLogicPipeline
from skeleton.pipelines.npc import NpcPipeline


def test_emit_returns_published_event_with_linkable_identity():
    bus = EventBus()
    seen = []
    bus.subscribe("*", seen.append)
    start = bus.emit("started", {"stage": 1})
    finish = bus.emit("finished", {}, correlation_id=start.correlation_id, causation_id=start.event_id)
    assert start is seen[0] and finish is seen[1]
    assert start.event_id == start.correlation_id
    assert finish.causation_id == start.event_id
    assert finish.event_id != start.event_id
    assert DomainEvent("legacy", {}, "correlation", 1).timestamp == 1


def test_npc_and_game_logic_emit_complete_correlated_event_chains(tmp_path):
    for pipeline, description in [(NpcPipeline, "a loyal guardian"), (GameLogicPipeline, "combat and exploration")]:
        bus = EventBus()
        events = []
        bus.subscribe("*", events.append)
        result = pipeline(bus=bus, root=tmp_path).run(description)
        assert result.to_dict()["quality"]
        start, quality, finish = events
        assert finish.topic.endswith("completed")
        assert quality.causation_id == finish.causation_id == start.event_id
        assert quality.correlation_id == finish.correlation_id == start.correlation_id
