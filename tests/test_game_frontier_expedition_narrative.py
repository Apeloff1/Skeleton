"""Canon dialog, quests, choices and non-forged game-state continuity."""
from dataclasses import replace
import pytest

from skeleton.jeeves.game_frontier_expedition import (
    ExpeditionAction,ExpeditionEpisode,ExpeditionError,
    Traveler,find_route,
)
from skeleton.jeeves.game_frontier_expedition_generation import (
    ArchipelagoProfile,author_archipelago,
)
from skeleton.jeeves.game_frontier_expedition_narrative import (
    StoryChoice,CanonScene,StoryBook,CanonDirector,original_expedition_story,
)

SOURCE="f"*64
GDD="b"*64


def game():
    w=author_archipelago("storyworld",SOURCE,ArchipelagoProfile(seed=17,islands=6))
    p=Traveler(
        permitted_modes=frozenset(("walk","rope_bridge","updraft","glide","airship")),
        flags=frozenset(("glider","airship_license")),max_stamina=1000,
    )
    return w,p


def test_original_three_act_story_has_playable_real_world_locations():
    w,_=game()
    book=original_expedition_story(w,GDD)
    assert [s.act for s in book.scenes]==[1,2,3]
    assert [s.waypoint for s in book.scenes]==[
        "harbor","island_001","island_006"]
    assert len(book.digest)==64
    book.validate_world(w)


def test_story_authoring_uses_gameplay_prerequisites_without_forging_game_flags():
    w,p=game()
    ep=ExpeditionEpisode(w,p)
    book=original_expedition_story(w,GDD)
    director=CanonDirector(book,w)
    assert [s.scene_id for s in director.offered(ep)]==["departure"]
    original_flags=set(ep.flags)
    first=director.choose(ep,"departure","chart")
    assert "map_promised" in director.flags
    assert set(ep.flags)==original_flags
    assert len(first.receipt)==64
    with pytest.raises(ExpeditionError,match="unavailable"):
        director.choose(ep,"departure","rescue")
    ep.step(ExpeditionAction("travel","launch_updraft"))
    assert [s.scene_id for s in director.offered(ep)]==["threshold"]
    second=director.choose(ep,"threshold","remember")
    assert second.previous_receipt==first.receipt
    assert "memory_kept" in director.flags
    path=find_route(w,p,w.destinations[0])
    # Replay the route to its real destination, not a dialogue shortcut.
    ep=ExpeditionEpisode(w,p)
    for eid in path.edge_ids:
        ep.step(ExpeditionAction("travel",eid))
    assert ep.won
    assert [s.scene_id for s in director.offered(ep)]==["arrival"]
    result=director.choose(ep,"arrival","archive")
    assert result.outcome=="Chronicle founded"
    assert "chronicle_written" in director.flags
    assert len(director.moments)==3


def test_story_cannot_trigger_in_foreign_world_or_wrong_position():
    w,p=game()
    director=CanonDirector(original_expedition_story(w,GDD),w)
    with pytest.raises(ExpeditionError,match="unavailable"):
        director.choose(ExpeditionEpisode(w,p),"arrival","archive")
    other=author_archipelago("storyworld",SOURCE,ArchipelagoProfile(seed=18,islands=6))
    with pytest.raises(ExpeditionError,match="source"):
        director.offered(ExpeditionEpisode(other,p))


def test_changed_gdd_changes_canon_identity_without_reusing_dialogue_receipts():
    w,p=game()
    a=original_expedition_story(w,GDD)
    b=original_expedition_story(w,"c"*64)
    assert a.digest!=b.digest
    director=CanonDirector(a,w)
    genesis=director.snapshot()
    with pytest.raises(ExpeditionError,match="another canonical"):
        CanonDirector.restore(b,ExpeditionEpisode(w,p),genesis)


def test_restorable_genesis_and_nonempty_replay_fail_closed():
    w,p=game()
    director=CanonDirector(original_expedition_story(w,GDD),w)
    initial=director.snapshot()
    assert CanonDirector.restore(director.book,ExpeditionEpisode(w,p),initial).snapshot()==initial
    director.choose(ExpeditionEpisode(w,p),"departure","chart")
    with pytest.raises(ExpeditionError,match="historical gameplay"):
        CanonDirector.restore(director.book,ExpeditionEpisode(w,p),director.snapshot())


@pytest.mark.parametrize("changes",(
    {"act":0},{"speaker":"unsafe name"},{"opening":""},{"repeatable":1},
))
def test_story_invalid_authored_scene_rejected(changes):
    base=CanonScene("a",1,"harbor","writer","Original dialogue",choices=(
        StoryChoice("yes","Agreed"),))
    with pytest.raises(ExpeditionError):
        replace(base,**changes)


def test_nonexistent_quest_prerequisites_cannot_launder_canon():
    with pytest.raises(ExpeditionError,match="never-produced"):
        StoryBook(SOURCE,GDD,(
            CanonScene("lost",1,"harbor","speaker","Hello",
                requires_story_flags=("never_received",),
                choices=(StoryChoice("yes","Yes"),)),
        ))
