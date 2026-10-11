"""Real NPC civic institutions: location-bound ballots and finite funded policies."""
from __future__ import annotations

from dataclasses import replace
import json

import pytest

from skeleton.game.generation.original_foundation_compiler import FoundationError
from skeleton.game.generation.original_world_living_10x_compiler import living_for
from skeleton.game.generation.original_world_npc_civics import (
    Assembly, Ballot, CivicInstitutions, PublicService, SCHEMA,
    validate_civics, propose_civic, settle_civic, civic_save,
    civic_restore, civic_report,
)
from skeleton.game.generation.original_world_product_session import (
    ProductAction, create_product, step_product, product_save,
    product_restore, validate_product,
)
from skeleton.game.generation.original_world_product_cli import parse_command


def original(n=2):
    law = living_for(0, "puzzle", "lattice", "trophic", "sandbox")
    return create_product(law.index, inhabitants=n)


def residents_present(state, *, hunger=4, health=20):
    people = tuple(replace(p, x=0, y=0, energy=0,
                           hunger=hunger, health=health)
                   for p in state.society.inhabitants)
    return replace(state, society=replace(state.society, inhabitants=people))


def propose(state, policy, citizen=0):
    return step_product(state, ProductAction(
        "npc", "propose", target=citizen, option=policy,
    ))[0]


def step(state):
    return step_product(state, ProductAction("causal", "end_turn"))[0]


def test_funded_food_law_requires_actual_votes_then_spends_a_real_meal():
    s = residents_present(original(2), hunger=4)
    starting_food = s.terrain.provisions
    starting_trust = s.living.spatial.game.causal.trust
    s = propose(s, "food-aid")
    assert s.terrain.provisions == starting_food - 1
    assert s.living.spatial.game.causal.trust == starting_trust - 1
    assert s.cognition.civic.proposals[0].status == "pending"
    assert s.cognition.civic.active_mandate == ""
    s = step(s)
    council = s.cognition.civic
    assert council.active_mandate == "food-aid"
    assert council.proposals[0].status == "enacted"
    assert council.proposals[0].participating == (0, 1)
    assert sum(b.supports for b in council.proposals[0].ballots) == 2
    assert len(council.services) == 1
    served = council.services[0]
    assert served.mandate == "food-aid"
    assert served.spent == 1 and served.stock_kind == "food"
    assert served.resulting_value < served.prior_value
    assert s.terrain.provisions == starting_food - 2
    assert product_restore(product_save(s)) == s


def test_medical_charter_can_help_only_a_reachable_named_patient_with_water():
    s = residents_present(original(2), hunger=0, health=10)
    water = s.terrain.freshwater
    s = propose(s, "medical-aid")
    s = step(s)
    assert s.cognition.civic.active_mandate == "medical-aid"
    assert s.terrain.freshwater <= water - 1
    assert len(s.cognition.civic.services) >= 1
    record = s.cognition.civic.services[0]
    assert record.stock_kind == "water"
    assert record.resulting_value == record.prior_value + 2


def test_ill_or_absent_voters_cannot_forge_a_public_majority():
    s = original(2)
    s = propose(s, "conservation")
    # Citizens remain physically located, but no conscious participation.
    s = replace(s, society=replace(
        s.society,
        inhabitants=tuple(replace(p, health=0) for p in s.society.inhabitants),
    ))
    s = step(s)
    charter = s.cognition.civic.proposals[0]
    assert charter.status == "rejected"
    assert charter.participating == ()
    assert charter.ballots == ()
    assert not s.cognition.civic.active_mandate


def test_proposer_cannot_vote_twice_or_issue_unpaid_concurrent_proposals():
    s = original(2)
    s = propose(s, "food-aid")
    with pytest.raises(FoundationError):
        propose(s, "expedition")
    with pytest.raises(FoundationError):
        propose(s, "invented-policy")
    fake = replace(s.cognition.civic, proposals=(replace(
        s.cognition.civic.proposals[0],
        status="enacted", finalized_day=0,
        ballots=(Ballot(0, True, (0, 0), 5, 15, "valid vote"),
                 Ballot(0, True, (0, 0), 5, 15, "duplicated vote")),
        participating=(0, 0),
    ),))
    with pytest.raises(FoundationError):
        validate_civics(fake, s.society, s.terrain, s.cognition.day)


def test_public_policy_vote_uses_actual_hunger_not_preselected_outcome():
    s = residents_present(original(2), hunger=9)
    s = propose(s, "expedition")
    # Real high hunger overrides citizens' curiosity for an expedition.
    s = step(s)
    result = s.cognition.civic.proposals[0]
    assert result.status == "rejected"
    assert len(result.ballots) == 2
    assert not any(b.supports for b in result.ballots)
    assert s.cognition.civic.active_mandate == ""


def test_civic_archive_preserves_all_public_receipts_without_mutating_game():
    s = residents_present(original(2), hunger=4)
    s = step(propose(s, "food-aid"))
    audit = civic_save(s.cognition.civic)
    restored = civic_restore(audit, s.society, s.terrain, s.cognition.day)
    assert restored == s.cognition.civic
    assert civic_report(restored)["services_delivered"] == 1
    audit["payload"]["services"][0]["spent"] = 99
    with pytest.raises(FoundationError):
        civic_restore(audit, s.society, s.terrain, s.cognition.day)


def test_civic_support_does_not_create_food_when_store_is_empty():
    s = residents_present(original(2), hunger=4)
    s = propose(s, "food-aid")
    s = replace(s, terrain=replace(s.terrain, provisions=0))
    s = step(s)
    assert s.cognition.civic.active_mandate == "food-aid"
    assert s.terrain.provisions == 0
    assert s.cognition.civic.services == ()
    assert all(p.hunger > 0 for p in s.society.inhabitants)


def test_cli_policy_command_routes_to_actual_resident_sponsor():
    assert parse_command("npc propose 1 food-aid", (0, 0)) == ProductAction(
        "npc", "propose", target=1, option="food-aid",
    )
