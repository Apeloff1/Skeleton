"""The desk planner proves a plan, or it says why there isn't one."""
from __future__ import annotations

import pytest

from skeleton.local_ai.multi_turn import MultiTurnDesk
from skeleton.local_ai.proof_planner import PlanRejected, prove


def _forge():
    return [
        "the stove is cold",
        "to light the stove: need the stove is cold; gain the stove is lit; lose the stove is cold; cost 2",
        "to boil the kettle: need the stove is lit; gain the kettle is warm; cost 3",
        "to forge the blade: need the kettle is warm; gain the blade is forged; cost 4",
        "budget is 10",
    ]


def test_optimal_plan_skips_work_already_true_and_picks_the_cheap_action():
    proof = prove(_forge(), "the blade is forged")
    assert proof.status == "proved"
    assert [step.name for step in proof.steps] == [
        "light the stove",
        "boil the kettle",
        "forge the blade",
    ]
    assert proof.cost == 9
    assert proof.heuristic is not None and proof.heuristic <= proof.cost
    assert proof.critical_path == (
        "light the stove",
        "boil the kettle",
        "forge the blade",
    )
    assert proof.steps[1].support == (("stove is lit", "light the stove"),)

    warm = prove(
        [
            "the kettle is warm",
            "to boil the kettle: need the stove is lit; gain the kettle is warm; cost 3",
            "to forge the blade: need the kettle is warm; gain the blade is forged; cost 4",
        ],
        "the blade is forged",
    )
    assert [step.name for step in warm.steps] == ["forge the blade"]
    assert warm.cost == 4

    water = prove(
        [
            "the well is open",
            "to carry the water: need the well is open; gain the kettle is full; cost 5",
            "to pipe the water: need the well is open; gain the kettle is full; cost 2",
        ],
        "the kettle is full",
    )
    assert [step.name for step in water.steps] == ["pipe the water"]
    assert water.cost == 2
    assert water.heuristic == 2


def test_sussman_anomaly_unstacks_before_it_stacks():
    proof = prove(
        [
            "c is on a",
            "a is on table",
            "b is on table",
            "c is clear",
            "b is clear",
            "table is clear",
            "to put c on table: need c is clear and c is on a and table is clear; gain c is on table and a is clear; lose c is on a; cost 1",
            "to put b on c: need b is clear and c is clear and b is on table; gain b is on c; lose b is on table and c is clear; cost 1",
            "to put a on b: need a is clear and b is clear and a is on table; gain a is on b; lose a is on table and b is clear; cost 1",
        ],
        "a is on b and b is on c",
    )
    assert [step.name for step in proof.steps] == [
        "put c on table",
        "put b on c",
        "put a on b",
    ]
    assert proof.cost == 3
    assert proof.heuristic is not None and proof.heuristic <= proof.cost
    assert proof.parallel == (("put c on table",), ("put b on c",), ("put a on b",))


def test_parallel_levels_and_the_critical_path():
    proof = prove(
        [
            "the shop is open",
            "to cut the cloth: need the shop is open; gain the cloth is cut; cost 3",
            "to sew the thread: need the shop is open; gain the thread is ready; cost 1",
        ],
        "the cloth is cut and the thread is ready",
    )
    assert proof.status == "proved"
    assert proof.cost == 4
    assert proof.critical_path == ("cut the cloth",)
    assert proof.parallel == (("cut the cloth", "sew the thread"),)
    assert proof.heuristic == 3


def test_a_threat_is_kept_outside_the_causal_link():
    proof = prove(
        [
            "the gate is shut",
            "to open the gate: need the gate is shut; gain the gate is open; lose the gate is shut; cost 1",
            "to pass the gate: need the gate is open; gain we are through; cost 1",
            "to close the gate: need the gate is open; gain the gate is shut; lose the gate is open; cost 1",
        ],
        "we are through and the gate is shut",
    )
    assert [step.name for step in proof.steps] == [
        "open the gate",
        "pass the gate",
        "close the gate",
    ]
    assert proof.parallel == (
        ("open the gate",),
        ("pass the gate",),
        ("close the gate",),
    )


def test_rules_derive_facts_and_do_not_invent_actions():
    proof = prove(
        [
            "the stove is cold",
            "to light the stove: need the stove is cold; gain the stove is lit; cost 2",
            "if the stove is lit then the kettle is warm",
        ],
        "the kettle is warm",
    )
    assert [step.name for step in proof.steps] == ["light the stove"]
    assert proof.cost == 2

    already = prove(
        ["the stove is lit", "if the stove is lit then the kettle is warm"],
        "the kettle is warm",
    )
    assert already.steps == ()
    assert already.cost == 0
    assert already.status == "proved"

    missing = prove(["the stove is cold"], "the blade is forged")
    assert missing.status == "infeasible"
    assert missing.steps == ()
    assert missing.missing == ("blade is forged",)


def test_contradiction_budget_and_secrets_fail_closed():
    clash = prove(["the stove is lit", "not the stove is lit"], "the stove is lit")
    assert clash.status == "contradicted"
    assert clash.conflict == ("stove is lit", "not stove is lit")
    assert clash.steps == ()

    mutex = prove(
        [
            "the stove is lit",
            "the stove is cold",
            "never both the stove is lit and the stove is cold",
        ],
        "the kettle is warm",
    )
    assert mutex.status == "contradicted"
    assert mutex.conflict == ("stove is cold", "stove is lit")

    over = prove(
        [
            "the well is open",
            "to pipe the water: need the well is open; gain the kettle is full; cost 5",
            "budget is 2",
        ],
        "the kettle is full",
    )
    assert over.status == "infeasible"
    assert over.cost == 5
    assert over.budget == 2
    assert [step.name for step in over.steps] == ["pipe the water"]
    assert "cost exceeds budget" in over.render()
    assert "cost 5 budget 2" in over.render()

    secret = "api_key=local-secret"
    with pytest.raises(PlanRejected) as raised:
        prove([secret], "the kettle is warm")
    assert str(raised.value) == "payload refused"
    assert secret not in str(raised.value)


def test_heuristic_prunes_a_decoy_chain():
    facts = ["ready is true"]
    for index in range(1, 9):
        need = "ready is true" if index == 1 else f"step {index - 1} is done"
        facts.append(
            f"to make step {index}: need {need}; gain step {index} is done; cost 1"
        )
        facts.append(
            f"to waste step {index}: need {need}; gain step {index} is wasted; cost 1"
        )
    proof = prove(facts, "step 8 is done")
    assert [step.name for step in proof.steps] == [f"make step {index}" for index in range(1, 9)]
    assert proof.cost == 8
    assert proof.heuristic == 8
    assert proof.expansions == 9
    assert proof.digest == prove(facts, "step 8 is done").digest


def test_desk_plan_uses_memory_and_does_not_call_a_model(tmp_path):
    desk = MultiTurnDesk(tmp_path)
    run = desk.run(
        [
            "remember the well is open",
            "remember to carry the water: need the well is open; gain the kettle is full; cost 5",
            "remember to pipe the water: need the well is open; gain the kettle is full; cost 2",
            "plan the kettle is full",
        ]
    )
    turn = run.turns[-1]
    assert turn.verb == "plan"
    assert turn.status == "ok"
    assert turn.verified is True
    assert turn.model_called is False
    assert turn.local_model_used is False
    assert run.model_called is False
    assert "pipe the water" in turn.answer
    assert "carry the water" not in turn.answer
    assert turn.answer.startswith("proved kettle is full")

    blocked = desk.run(["plan the blade is forged"])
    assert blocked.turns[-1].status == "refused"
    assert "missing blade is forged" in blocked.turns[-1].answer
