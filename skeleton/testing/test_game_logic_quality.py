"""Game-logic quality integration tests."""
from __future__ import annotations

from skeleton.kernel.events import EventBus
from skeleton.pipelines.game_logic import GameLogicPipeline


def test_game_logic_pipeline_attaches_quality_contract():
    pipe = GameLogicPipeline(bus=EventBus())
    spec = pipe.run("quadratic credits arena combat", title="Arena Ops", curve="quadratic", currency="credits")
    payload = spec.to_dict()
    assert payload["quality"]["accepted"] is True
    assert payload["quality"]["quality"]["metadata"]["kind"] == "pipeline"
    assert payload["quality"]["quality"]["metadata"]["pipeline"] == "game_logic"
    assert payload["quality_stats"]["runs"] == 1
