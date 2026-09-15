import pytest

from skeleton.kernel.errors import ValidationError
from skeleton.pipelines.lorebuffa_dialogue import (
    LorebuffaDialogueRuntime,
    completed_marina_dialogue,
)


def test_completed_marina_dialogue_is_closed():
    graph = completed_marina_dialogue()
    LorebuffaDialogueRuntime.validate_graph(graph)
    destinations = {
        option["next"]
        for node in graph.values()
        for option in node.get("options", [])
    }
    assert destinations <= set(graph)


def test_requirement_gate_blocks_missing_bottle():
    runtime = LorebuffaDialogueRuntime()
    state = runtime.new_state()
    runtime.choose(state, "info")
    runtime.choose(state, "bottle_info")

    give_bottle = next(
        option
        for option in runtime.available_options(state)
        if option["id"] == "give_bottle"
    )
    assert give_bottle["enabled"] is False
    assert give_bottle["blocked_reason"] == "requires_item:james_bottle"
    with pytest.raises(ValidationError):
        runtime.choose(state, "give_bottle")


def test_full_rescue_path_applies_state_and_accepts_quest():
    runtime = LorebuffaDialogueRuntime()
    state = runtime.new_state(inventory={"james_bottle"})

    runtime.choose(state, "info")          # +5
    runtime.choose(state, "bottle_info")   # +25
    turn = runtime.choose(state, "give_bottle")  # +30 choice, +40 node reward

    assert turn.node_id == "receives_bottle"
    assert state.reputation == 100
    assert state.trust_level == "max"
    assert "rescue_james" in state.quests
    assert "receives_bottle" in state.claimed_rewards

    turn = runtime.choose(state, "accept_help")  # +20
    assert turn.node_id == "rescue_mission_planning"
    assert turn.quest_offer["id"] == "rescue_james_goldscale"
    assert state.reputation == 120
    assert state.ended is True

    offer = runtime.accept_quest(state)
    assert offer["id"] == "rescue_james_goldscale"
    assert "rescue_james_goldscale" in state.quests


def test_replay_is_deterministic():
    runtime = LorebuffaDialogueRuntime()
    choices = ("info", "bottle_info", "give_bottle", "accept_help")
    first = runtime.replay(choices, inventory={"james_bottle"}).snapshot()
    second = runtime.replay(choices, inventory={"james_bottle"}).snapshot()
    assert first == second


def test_runtime_graph_is_defensive_copy():
    runtime = LorebuffaDialogueRuntime()
    graph = runtime.graph
    graph["greeting"]["text"] = "mutated"
    assert runtime.start().text != "mutated"


def test_validation_rejects_dangling_destination():
    bad = {
        "greeting": {
            "text": "hello",
            "options": [{"id": "go", "text": "go", "next": "missing"}],
        }
    }
    with pytest.raises(ValidationError):
        LorebuffaDialogueRuntime(bad)
