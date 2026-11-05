"""Branch-exclusive NPC testimony may disagree without a single-path contradiction."""
from __future__ import annotations

from copy import deepcopy

from skeleton.jeeves.worlds.cast import approve_cast, propose_cast
from skeleton.jeeves.worlds.testimony import (
    propose_testimony, edit_testimony, prove_testimony, replay_testimony,
)
from skeleton.jeeves.worlds.world_canon import propose, prove


def test_exclusive_endings_have_distinct_testimony():
    world = propose(world_id="harbor", premise="An original disputed treaty",
                    protagonist="Mara", region="Glass Bay", goal="Sign the treaty")
    world["scenes"].append({"id": "refusal", "title": "Refusal",
                            "narrative": "The council rejects the terms."})
    world["choices"].append({"id": "refuse_goal", "from": "opening", "to": "refusal",
                             "label": "Refuse the treaty", "requires": [], "grants": []})
    world["endings"].append({"scene": "refusal", "label": "Treaty rejected"})
    prove(world)
    cast = propose_cast(world, npc_id="tala", npc_name="Tala",
                        npc_line="The council remembers the debate.")
    cast["characters"][0]["scenes"] = ["opening", "refusal", "resolution"]
    cast = approve_cast(cast, world, "Original branch-aware witness")
    source = propose_testimony(
        world, cast, prompt="Tala reports the council decision",
        statement_id="a_signed", actor="tala", scene="resolution",
        choice="pursue_goal", claim="treaty_signed", stance="supports",
        text="The treaty was signed.", provenance="firsthand")
    denial = deepcopy(source["statements"][0])
    denial.update({"id": "z_refused", "scene": "refusal", "choice": "refuse_goal",
                   "stance": "denies", "text": "The treaty was rejected."})
    source = edit_testimony(source, world, cast,
                            {"action": "add_statement", "value": denial})
    proof = prove_testimony(source, world, cast)
    assert proof["statement_witnesses"]["a_signed"] == ["pursue_goal"]
    assert proof["statement_witnesses"]["z_refused"] == ["refuse_goal"]
    signed = replay_testimony(source, world, cast, ["pursue_goal"])
    refused = replay_testimony(source, world, cast, ["refuse_goal"])
    assert signed["revealed_ids"] == ["a_signed"]
    assert refused["revealed_ids"] == ["z_refused"]
