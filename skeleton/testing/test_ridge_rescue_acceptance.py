"""End-to-end proof from real source, through movement and crafting, to portable verified victory."""
from copy import deepcopy
import pytest
from skeleton.game.gameplay.ridge_rescue.acceptance import run_acceptance, acceptance_actions, ACCEPTANCE_SOURCE
from skeleton.game.gameplay.ridge_rescue.custody import verify_run, digest, CustodyError
from skeleton.game.gameplay.ridge_rescue.engine import replay, RescueError
from skeleton.game.gameplay.ridge_rescue.schema import parse_world

@pytest.mark.parametrize("ending", ["protect", "salvage"])
def test_earned_victory_from_unmodified_source(ending):
    bundle = run_acceptance(ending)
    verified = verify_run(bundle)
    assert verified["state"]["status"] == f"won:{ending}"
    assert verified["state"]["turn"] == len(acceptance_actions(ending))
    assert verified["state"]["civilians"] == {"tavi": "rescued"}
    assert verified["state"]["flags"]["choice"] == ending

def test_earned_beacon_requires_real_finite_crafting():
    bundle = run_acceptance("protect")
    events = bundle["payload"]["state"]["events"]
    assert "gather:kindling:wood" in events
    assert events.count("gather:ridge_ore:ore") == 2
    assert "craft:signal" in events
    assert "beacon:lit" in events
    assert events.index("craft:signal") < events.index("beacon:lit") < events.index("ending:protect")

def test_salvage_does_not_fake_beacon():
    bundle = run_acceptance("salvage")
    assert bundle["payload"]["state"]["flags"]["beacon"] is False
    assert "beacon:lit" not in bundle["payload"]["state"]["events"]

def test_protection_without_crafting_fails_closed():
    world = parse_world(ACCEPTANCE_SOURCE.read_bytes())
    illegal = acceptance_actions("salvage")[:-1] + [{"verb": "evacuate", "choice": "protect"}]
    with pytest.raises(RescueError):
        replay(world, illegal)

def test_rehashed_ending_swap_is_rejected():
    bundle = run_acceptance("salvage")
    bundle["payload"]["state"]["status"] = "won:protect"
    bundle["sha256"] = digest(bundle["payload"])
    with pytest.raises(CustodyError):
        verify_run(bundle)

def test_original_source_and_action_list_immutable():
    world = parse_world(ACCEPTANCE_SOURCE.read_bytes())
    actions = acceptance_actions("protect")
    prior = deepcopy(actions)
    replay(world, actions)
    assert actions == prior
