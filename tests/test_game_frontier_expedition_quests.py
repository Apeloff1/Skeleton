"""Three playable endings are selected only after actual world traversal."""
from copy import deepcopy
from dataclasses import replace
import pytest

from skeleton.jeeves.game_frontier_expedition import (
    ExpeditionAction,ExpeditionEpisode,ExpeditionError,find_route,
)
from skeleton.jeeves.game_frontier_expedition_generation import (
    ArchipelagoProfile,author_archipelago,
)
from skeleton.jeeves.game_frontier_expedition_campaign import original_campaign_player
from skeleton.jeeves.game_frontier_expedition_narrative import (
    CanonDirector,original_expedition_story,
)
from skeleton.jeeves.game_frontier_expedition_quests import (
    Ending,QuestStage,QuestBook,QuestDirector,original_quest_book,
)


def game():
    world=author_archipelago(
        "questworld","f"*64,ArchipelagoProfile(seed=18,islands=6),
    )
    player=original_campaign_player()
    session=ExpeditionEpisode(world,player)
    story=CanonDirector(original_expedition_story(world,"c"*64),world)
    book=original_quest_book(session,story.book)
    return world,player,session,story,QuestDirector(book,story,session)


def complete_game(world,player,session):
    route=find_route(world,player,world.destinations[0])
    for eid in route.edge_ids:
        session.step(ExpeditionAction("travel",eid))
    assert session.won


def test_quest_book_has_three_original_canon_endings():
    world,player,session,story,quests=game()
    assert {x.ending_id for x in quests.book.endings}=={
        "cartographer","rescuer","wanderer"}
    assert quests.book.world_digest==world.digest
    assert quests.book.story_digest==story.book.digest
    assert len(quests.book.digest)==64


@pytest.mark.parametrize("first_choice,ending",(
    ("chart","cartographer"),("rescue","rescuer"),
))
def test_two_distinct_endings_require_actual_quest_and_dialogue(first_choice,ending):
    world,player,gameplay,story,quests=game()
    story.choose(gameplay,"departure",first_choice)
    assert quests.advance(gameplay,story)[0]["step"]==1
    assert len(quests.flags)==1
    gameplay.step(ExpeditionAction("travel","launch_updraft"))
    assert quests.advance(gameplay,story)[0]["step"]==2
    story.choose(gameplay,"threshold","remember")
    # Actually follow authored game route to the final location.
    return_trip=find_route(world,player,world.destinations[0],start=gameplay.position)
    for eid in return_trip.edge_ids:
        gameplay.step(ExpeditionAction("travel",eid))
    assert gameplay.won
    assert quests.advance(gameplay,story)[0]["step"]==3
    story.choose(gameplay,"arrival","archive")
    chosen=quests.ending(gameplay,story)
    assert chosen["ending_id"]==ending
    assert chosen["victory"]
    assert chosen["source"]==quests.book.digest
    assert len(chosen["receipt_digest"])==64


def test_default_wanderer_ending_requires_real_win_not_trivial_script_claim():
    world,player,session,story,quests=game()
    with pytest.raises(ExpeditionError,match="without completing"):
        quests.ending(session,story)
    complete_game(world,player,session)
    outcome=quests.ending(session,story)
    assert outcome["ending_id"]=="wanderer"
    assert outcome["quest_flags"]==[]


def test_quest_progress_does_not_mutate_inventory_or_gameplay_flags():
    world,player,session,story,quests=game()
    game_flags=set(session.flags)
    story.choose(session,"departure","chart")
    assert quests.advance(session,story)
    assert set(session.flags)==game_flags
    assert "chart_contract" not in session.flags
    assert "chart_contract" in quests.flags
    assert quests.advance(session,story)==()


def test_story_source_change_rejects_quest_reuse_and_false_ending():
    world,player,session,story,quests=game()
    other=CanonDirector(original_expedition_story(world,"d"*64),world)
    with pytest.raises(ExpeditionError,match="unchanged game and canon"):
        quests.advance(session,other)
    with pytest.raises(ExpeditionError,match="foreign gameplay"):
        quests.ending(session,other)


def test_duplicate_unreachable_quest_endings_are_rejected():
    world,player,session,story,quests=game()
    with pytest.raises(ExpeditionError,match="impossible quest"):
        QuestBook(world.digest,story.book.digest,quests.book.quests,(
            Ending("impossible","An Impossible End",needs_quest_flags=("never_earned",)),
            Ending("default","Default"),
        ))


def test_story_and_game_snapshots_appear_in_each_quest_step_receipt():
    world,player,session,story,quests=game()
    initial=quests.snapshot()
    assert initial["progress"]=={
        "chart_the_islands":0,"keep_the_promise":0}
    story.choose(session,"departure","rescue")
    step=quests.advance(session,story)[0]
    assert step["game_receipt"]==session.snapshot()["receipt_head"]
    assert step["story_receipt"]==story.head
    assert step["receipt"]==quests.head
    assert step["previous"]!=step["receipt"]
    assert initial["head"]!=quests.snapshot()["head"]
