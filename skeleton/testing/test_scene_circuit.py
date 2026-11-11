"""Circuit gate, switch, inventory, save and replay acceptance."""
import copy
import json

import pytest

from skeleton.game.gameplay.scene_circuit import (
    SCHEMA, cli, export_circuit, import_circuit, new_circuit,
    normalize_circuit, original_circuit, resume_circuit,
    simulate_circuit, verify_circuit,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError, verify_session


def test_demo_unlocks_gate_and_reaches_real_scene_ending():
    source, actions = original_circuit()
    saved = simulate_circuit(source, actions)
    assert saved["state"]["scene"]["state"]["phase"] == "won"
    assert saved["state"]["scene"]["state"]["scene_id"] == "sanctuary"
    assert saved["state"]["switches"]["quay_lantern"] is True
    assert verify_session(saved["state"]["scene"]) == saved["state"]["scene"]
    assert verify_circuit(json.loads(json.dumps(saved))) == saved


def test_locked_gate_requires_switch_and_canonical_inventory():
    source, actions = original_circuit()
    with pytest.raises(SceneTravelError, match="locked"):
        simulate_circuit(source, [actions[1], actions[2]])
    with pytest.raises(SceneTravelError, match="uncollected"):
        simulate_circuit(source, [actions[0], actions[2]])
    with pytest.raises(SceneTravelError, match="not in"):
        simulate_circuit(source, [{"kind": "toggle", "switch_id": "gate_pulse"}])


def test_toggle_resume_and_portable_bundle():
    source, actions = original_circuit()
    sequence = [actions[0], actions[0], *actions]
    first = simulate_circuit(source, sequence[:2])
    complete = simulate_circuit(source, sequence)
    assert resume_circuit(json.loads(json.dumps(first)), sequence[2:]) == complete
    assert import_circuit(json.loads(json.dumps(export_circuit(complete)))) == complete


@pytest.mark.parametrize("mutate", [
    lambda x: x.update(schema_version="future"),
    lambda x: x["switches"][0].update(initial_on=1),
    lambda x: x["switches"].append(x["switches"][0]),
    lambda x: x["switches"][0].update(scene_id="sanctuary"),
    lambda x: x["gates"][0].update(exit_id="not_an_exit"),
    lambda x: x["gates"][0].update(requires_on=["missing"]),
    lambda x: x["gates"][0].update(requires_off=["quay_lantern"]),
    lambda x: x["gates"].append(x["gates"][0]),
])
def test_invalid_authored_circuit_fails_closed(mutate):
    source, _ = original_circuit()
    mutate(source)
    with pytest.raises(SceneTravelError):
        normalize_circuit(source)


@pytest.mark.parametrize("mutate", [
    lambda x: x["state"]["switches"].update(quay_lantern=False),
    lambda x: x["state"]["scene"]["state"].update(scene_id="sanctuary"),
    lambda x: x["journal"][0]["action"].update(switch_id="gate_pulse"),
    lambda x: x["journal"][0].update(receipt="0" * 64),
    lambda x: x["save"].update(parent_save_digest=None),
    lambda x: x.update(source_digest="0" * 64),
    lambda x: x.update(event_bus_digest="0" * 64),
])
def test_mutated_save_cannot_unlock_gate(mutate):
    source, actions = original_circuit()
    saved = copy.deepcopy(simulate_circuit(source, actions))
    mutate(saved)
    with pytest.raises(SceneTravelError):
        verify_circuit(saved)


def test_invalid_action_preserves_original_checkpoint():
    source, _ = original_circuit()
    checkpoint = new_circuit(source)
    with pytest.raises(SceneTravelError):
        resume_circuit(checkpoint, [{"kind": "travel", "exit_id": "north"}])
    assert checkpoint["state"]["tick"] == 0
    assert checkpoint["journal"] == []


def test_cli_demo_preview_and_bad_input(capsys):
    source, _ = original_circuit()
    assert cli(["demo"]) == 0
    assert json.loads(capsys.readouterr().out)["state"]["scene"]["state"]["phase"] == "won"
    assert cli(["preview", "--source-json", json.dumps(source)]) == 0
    assert json.loads(capsys.readouterr().out)["schema_version"] == SCHEMA
    assert cli(["preview", "--source-json", "{}"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
