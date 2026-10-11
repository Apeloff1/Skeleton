"""Verifiable physical mentorship and professional mobility: no skill shortcuts."""
from __future__ import annotations
from dataclasses import replace
import pytest

from skeleton.game.generation.original_foundation_compiler import FoundationError
from skeleton.game.generation.original_world_living_10x_compiler import living_for
from skeleton.game.generation.original_world_npc_apprenticeships import (
    Apprenticeship, TeachingLedger, enroll, cancel_enrollment,
    settle_training, validate_teaching, training_save, training_restore,
    training_report,
)
from skeleton.game.generation.original_world_product_session import (
    ProductAction, create_product, product_save, product_restore,
    step_product, validate_product,
)
from skeleton.game.generation.original_world_product_cli import parse_command


def original(n=2):
    rule = living_for(0, "puzzle", "lattice", "trophic", "sandbox")
    return create_product(rule.index, inhabitants=n)


def physically_present(state):
    first, second, *rest = state.society.inhabitants
    people = (
        replace(first, x=0, y=0, energy=0,
                profession="forager", experience=3),
        replace(second, x=0, y=0, energy=0, profession="scout"),
        *rest,
    )
    return replace(state, society=replace(
        state.society, inhabitants=tuple(people)
    ))


def issue(state, verb, *, target=0, option=""):
    return step_product(state, ProductAction(
        "npc", verb, target=target, option=option,
    ))[0]


def tick(state):
    return step_product(state, ProductAction("causal", "end_turn"))[0]


def test_in_person_three_real_lessons_pay_food_and_gain_new_profession():
    state = physically_present(original())
    food, trust = (state.terrain.provisions,
                   state.living.spatial.game.causal.trust)
    state = issue(state, "mentor", target=0, option="1")
    assert state.living.spatial.game.causal.trust == trust - 1
    assert state.cognition.training.records[0].status == "active"
    assert state.society.inhabitants[1].profession == "scout"
    for day in (1, 2, 3):
        state = tick(state)
        ledger = state.cognition.training.records[0]
        assert ledger.lessons == day
        assert ledger.proof_days == tuple(range(1, day + 1))
        assert state.terrain.provisions == food - day
        assert state.cognition.training.food_spent == day
    assert state.cognition.training.completed == 1
    assert state.society.inhabitants[1].profession == "forager"
    assert state.society.inhabitants[1].experience >= 6
    assert product_restore(product_save(state)) == state
    assert validate_product(state)


def test_no_unearned_professions_when_master_lacks_actual_experience():
    state = original(2)
    with pytest.raises(FoundationError):
        issue(state, "mentor", target=0, option="1")
    assert state.cognition.training.records == ()
    assert state.living.spatial.game.causal.trust == 9


def test_one_mentor_cannot_duplicate_same_day_training_or_certify_self():
    s = physically_present(original())
    with pytest.raises(FoundationError):
        issue(s, "mentor", target=0, option="0")
    s = issue(s, "mentor", target=0, option="1")
    with pytest.raises(FoundationError):
        issue(s, "mentor", target=0, option="1")
    s = tick(s)
    assert s.cognition.training.records[0].proof_days == (1,)
    assert s.cognition.training.records[0].lessons == 1


def test_apprenticeship_pause_requires_actual_two_bodies_in_same_place():
    s = physically_present(original())
    s = issue(s, "mentor", target=0, option="1")
    apprentice = replace(s.society.inhabitants[1], x=1, y=0)
    s = replace(s, society=replace(s.society, inhabitants=(
        s.society.inhabitants[0], apprentice,
    )))
    s = tick(s)
    assert s.cognition.training.records[0].lessons == 0
    assert s.cognition.training.food_spent == 0


def test_learning_consumes_real_food_and_stops_when_warehouse_is_empty():
    s = physically_present(original())
    s = issue(s, "mentor", target=0, option="1")
    s = replace(s, terrain=replace(s.terrain, provisions=0))
    s = tick(s)
    assert s.cognition.training.food_spent == 0
    assert s.cognition.training.records[0].lessons == 0
    assert s.society.inhabitants[1].profession == "scout"


def test_cancellation_preserves_paid_history_and_prevents_future_lessons():
    s = physically_present(original())
    s = issue(s, "mentor", target=0, option="1")
    s = tick(s)
    s = issue(s, "cancel_mentorship", target=0)
    assert s.cognition.training.records[0].status == "cancelled"
    assert s.cognition.training.records[0].lessons == 1
    s = tick(s)
    assert s.cognition.training.records[0].lessons == 1
    assert s.cognition.training.food_spent == 1
    with pytest.raises(FoundationError):
        issue(s, "cancel_mentorship", target=0)


def test_signed_hash_training_save_roundtrip_and_tamper_detection():
    s = physically_present(original())
    s = issue(s, "mentor", target=0, option="1")
    s = tick(s)
    snapshot = training_save(s.cognition.training)
    restored = training_restore(snapshot, s.society, s.terrain)
    assert restored == s.cognition.training
    snapshot["payload"]["food_spent"] = 0
    with pytest.raises(FoundationError):
        training_restore(snapshot, s.society, s.terrain)


def test_spurious_three_credential_lessons_without_paid_stock_are_denied():
    s = original()
    bogus = TeachingLedger(
        records=(Apprenticeship(0, 0, 1, "forager", 0, 3,
                                 "completed", (1, 2, 3)),),
        next_id=1, completed=1, food_spent=0,
    )
    prior = replace(s.society, tick=3)
    with pytest.raises(FoundationError):
        validate_teaching(bogus, prior, s.terrain)


def test_training_report_contains_real_receipts_and_cli_parser_is_actionable():
    s = physically_present(original())
    s = issue(s, "mentor", target=0, option="1")
    report = training_report(s.cognition.training)
    assert report["recorded_apprenticeships"][0]["mentor"] == 0
    assert report["recorded_apprenticeships"][0]["apprentice"] == 1
    assert report["actual_training_food_spent"] == 0
    assert parse_command("npc mentor 0 1", (0, 0)) == ProductAction(
        "npc", "mentor", target=0, option="1",
    )
    assert parse_command("npc cancel_mentorship 0", (0, 0)).target == 0
