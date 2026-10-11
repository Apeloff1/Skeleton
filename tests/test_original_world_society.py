"""Autonomous resident and living campaign integration tests."""
from __future__ import annotations

from dataclasses import asdict, replace
import json

import pytest

from skeleton.game.generation.original_world_campaign import (
    CampaignAction, CampaignError, create_campaign, step,
)
from skeleton.game.generation.original_world_society import (
    JOBS, SOCIAL_ACTIONS, NAMES, SocietyAction, create_society,
    society_action, society_tick, validate_society,
)
from skeleton.game.generation.original_world_living_session import (
    create_living_session, living_restore, living_save, living_step,
    replay_living, validate_living_session,
)


def total_resources(world, society, resource: str, village_resource: str) -> int:
    return (
        sum(getattr(tile, resource) for tile in world.sectors)
        + sum(getattr(village, village_resource) for village in society.villages)
    )


def test_real_residents_have_distinct_jobs_and_homes() -> None:
    world = create_campaign("serenity-05", "residents")
    state = create_society(world)
    validate_society(state, world)
    assert len(state.residents) == 12
    assert len(state.villages) == 3
    assert {resident.profession for resident in state.residents} == set(JOBS)
    assert {resident.name for resident in state.residents} == set(NAMES)
    assert {resident.home for resident in state.residents} == {0, 4, 8}
    assert all(resident.energy > 0 for resident in state.residents)


def test_autonomous_jobs_consume_actual_world_resources() -> None:
    world = create_campaign("ecology-03", "autonomous-economy")
    society = create_society(world)
    new_world, _ = step(world, CampaignAction("end_turn"))
    before_food = total_resources(new_world, society, "food", "food")
    before_wood = total_resources(new_world, society, "wood", "timber")
    after_world, after_society, receipt = society_tick(new_world, society)
    assert after_society.day == 1
    assert receipt.event_id == after_society.event_head
    assert len(receipt.consequences) > 0
    # First day hunger is below the consumption threshold. Jobs may
    # transfer food and timber, but must not conjure them from nothing.
    assert total_resources(after_world, after_society, "food", "food") == before_food
    assert total_resources(after_world, after_society, "wood", "timber") == before_wood
    assert any(r.location != r.home for r in after_society.residents)
    validate_society(after_society, after_world)


def test_personal_relationships_are_distinct_from_collective_trust() -> None:
    world = create_campaign("serenity-05")
    soc = create_society(world)
    after_world, after_soc, receipt = society_action(
        world, soc, SocietyAction("greet", resident=0)
    )
    assert after_world.action_points == world.action_points - 1
    assert after_soc.residents[0].trust == soc.residents[0].trust + 1
    assert after_soc.residents[1] == soc.residents[1]
    assert after_soc.event_count == 1
    assert receipt.event_id == after_soc.event_head


def test_village_exchanges_are_two_sided_no_resource_creation() -> None:
    world = create_campaign("civilization-01")
    soc = create_society(world)
    player_food = world.food
    village_food = soc.villages[0].food
    w, s, _ = society_action(world, soc, SocietyAction("trade_food", 0, 2))
    assert w.food == player_food + 2
    assert s.villages[0].food == village_food - 2
    assert w.coins == world.coins - 4
    assert s.villages[0].funds == soc.villages[0].funds + 4
    w, s, _ = society_action(w, s, SocietyAction("give_food"))
    assert w.food + s.villages[0].food == player_food + village_food
    assert s.residents[0].trust > soc.residents[0].trust


def test_petition_approved_project_spends_materials() -> None:
    world = create_campaign("civilization-01")
    soc = create_society(world)
    world, soc, _ = society_action(world, soc, SocietyAction("petition"))
    assert soc.council == 1
    wood, stone = world.wood, world.stone
    world, soc, _ = society_action(world, soc, SocietyAction("commission"))
    assert soc.council == 0
    assert soc.villages[0].projects == 1
    assert world.wood == wood - 1
    assert world.stone == stone - 1


def test_companion_requires_relationship_and_consent() -> None:
    world = create_campaign("serenity-05")
    soc = create_society(world)
    with pytest.raises(CampaignError):
        society_action(world, soc, SocietyAction("invite"))
    world, soc, _ = society_action(world, soc, SocietyAction("greet"))
    world, soc, _ = society_action(world, soc, SocietyAction("invite"))
    assert soc.residents[0].following
    world, soc, _ = society_action(world, soc, SocietyAction("dismiss"))
    assert not soc.residents[0].following


def test_integrated_session_moves_followers_on_actual_edges() -> None:
    session = create_living_session("topology-02", "companions")
    session, _ = living_step(session, SocietyAction("greet"))
    session, _ = living_step(session, SocietyAction("invite"))
    session, _ = living_step(session, CampaignAction("move", target=1))
    assert session.campaign.position == 1
    assert session.society.residents[0].location == 1
    assert session.society.residents[0].following
    session, _ = living_step(session, CampaignAction("end_turn"))
    assert session.campaign.turn == session.society.day == 1
    validate_living_session(session)


def test_social_actions_do_not_overwrite_campaign_and_world_receipts() -> None:
    session = create_living_session("civilization-01", "history")
    a, first = living_step(session, SocietyAction("greet"))
    b, second = living_step(a, CampaignAction("pledge"))
    c, third = living_step(b, CampaignAction("end_turn"))
    assert first.event_hash != second.event_hash != third.event_hash
    assert c.event_count == 3
    assert c.campaign.event_count == 2
    assert c.society.event_count == 2
    assert c.event_head == third.event_hash


def test_living_session_save_restore_and_replay() -> None:
    actions = (
        SocietyAction("greet"),
        CampaignAction("pledge"),
        CampaignAction("end_turn"),
        CampaignAction("forage"),
        CampaignAction("move", target=1),  # travel to the working resident
        SocietyAction("interview"),
        CampaignAction("end_turn"),
    )
    a, evidence = replay_living("serenity-05", "replay", actions)
    b, again = replay_living("serenity-05", "replay", actions)
    assert a == b and evidence == again
    assert a.event_count == len(actions)
    assert living_restore(living_save(a)) == a
    corrupt = json.loads(living_save(a))
    corrupt["payload"]["society"]["council"] = 100
    with pytest.raises(CampaignError):
        living_restore(json.dumps(corrupt))


@pytest.mark.parametrize("bad", [
    SocietyAction("missing"), SocietyAction("greet", resident=-1),
    SocietyAction("greet", resident=12), SocietyAction("greet", resident=True),
    SocietyAction("greet", amount=0), SocietyAction("greet", amount=4),
    SocietyAction("greet", amount=True),
])
def test_invalid_social_actions_cannot_mutate_world(bad: SocietyAction) -> None:
    world = create_campaign("serenity-05")
    society = create_society(world)
    snapshot = (asdict(world), asdict(society))
    with pytest.raises(CampaignError):
        society_action(world, society, bad)
    assert (asdict(world), asdict(society)) == snapshot


def test_exhausted_resources_do_not_allow_fake_economic_production() -> None:
    world = create_campaign("serenity-05")
    society = create_society(world)
    depleted = replace(society.villages[0], food=0, timber=0, funds=0)
    soc = replace(society, villages=(depleted, *society.villages[1:]))
    with pytest.raises(CampaignError):
        society_action(world, soc, SocietyAction("trade_food"))
    with pytest.raises(CampaignError):
        society_action(world, soc, SocietyAction("trade_wood"))


def test_society_staleness_and_identity_fail_closed() -> None:
    world = create_campaign("serenity-05")
    society = create_society(world)
    progressed, _ = step(world, CampaignAction("end_turn"))
    with pytest.raises(CampaignError):
        validate_society(society, progressed)
    with pytest.raises(CampaignError):
        validate_society(replace(society, seed="forged"), world)
    with pytest.raises(CampaignError):
        validate_society(replace(society, day=2), world)
    with pytest.raises(CampaignError):
        replay_living("serenity-05", "seed", "text")
    with pytest.raises(CampaignError):
        living_step(create_living_session("serenity-05"), "unsupported")
