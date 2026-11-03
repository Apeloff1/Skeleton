"""Two-step rumor transfers and impossible same-choice knowledge teleportation."""
from __future__ import annotations

from copy import deepcopy
import pytest

from skeleton.jeeves.worlds.cast import approve_cast, propose_cast
from skeleton.jeeves.worlds.rumors import (
    propose_rumors, edit_rumors, prove_rumors, replay_rumors,
)
from skeleton.jeeves.worlds.world_canon import CanonError, propose, prove


def scenario():
    world = propose(world_id="harbor", premise="An original harbor whisper",
                    protagonist="Mara", region="Glass Bay", goal="Reach the archive")
    world["scenes"].append({"id": "midway", "title": "Midway",
                            "narrative": "A meeting by the old lantern."})
    world["choices"][0]["to"] = "midway"
    world["choices"].append({"id": "share_rumor", "from": "midway", "to": "resolution",
                             "label": "Pass on the message", "requires": [], "grants": []})
    prove(world)
    cast = propose_cast(world, npc_id="tala", npc_name="Tala",
                        npc_line="The harbor keeps its secrets.")
    cast["characters"][0]["scenes"] = ["midway", "opening", "resolution"]
    cast["characters"].append({"id": "luka", "name": "Luka", "role": "npc",
                                "scenes": ["resolution"], "traits": []})
    cast = approve_cast(cast, world, "Original two-NPC rumor route")
    source = propose_rumors(
        world, cast, prompt="Tala shares news with Luka",
        rumor_id="archive_open", claim="archive_status", stance="supports",
        origin="tala", seed_choice="pursue_goal", text="The archive is open.")
    route = {"id": "tala_to_luka", "rumor": "archive_open", "from_actor": "tala",
             "to_actor": "luka", "choice": "share_rumor", "scene": "resolution"}
    source = edit_rumors(source, world, cast, {"action": "add_route", "value": route})
    return world, cast, source


def test_two_choice_causal_delivery():
    world, cast, source = scenario()
    proof = prove_rumors(source, world, cast)
    assert proof["delivery_witnesses"]["route:tala_to_luka"] == [
        "pursue_goal", "share_rumor"]
    replay = replay_rumors(source, world, cast, ["pursue_goal", "share_rumor"])
    assert [entry["actor"] for entry in replay["steps"][1]["heard"]] == ["tala"]
    assert [entry["actor"] for entry in replay["steps"][2]["heard"]] == ["luka", "tala"]


def test_one_transition_cannot_seed_and_forward():
    world, cast, source = scenario()
    cast["characters"][1]["scenes"] = ["midway", "resolution"]
    source["cast_digest"] = __import__("skeleton.jeeves.worlds.world_canon",
                                       fromlist=["digest"]).digest(cast)
    bad = deepcopy(source)
    bad["routes"][0]["choice"] = "pursue_goal"
    bad["routes"][0]["scene"] = "midway"
    with pytest.raises(CanonError) as exc:
        prove_rumors(bad, world, cast)
    assert exc.value.code == "rumors_unreachable_delivery"
