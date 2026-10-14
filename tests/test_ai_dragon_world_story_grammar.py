"""Original genre-grammar gameplay from literary/film/game *principles*, not copies."""
from __future__ import annotations
from dataclasses import replace
import pytest

from skeleton.ai.webcrawler.dragon_world_codex import edit,unrank
from skeleton.ai.webcrawler.dragon_world_story_grammar import (
    SCHEMA,WORLD_FAMILIES,WORLD_ARCHETYPES,CONFLICTS,
    PERSPECTIVES,TIMELINES,STAGING,STORY_CHOICES,
    bible,open_story,story_options,choose,replay_story,story_report,
)


def test_original_story_library_uses_64_abstract_worlds_and_narrative_grammar():
    assert len(WORLD_FAMILIES)==8
    assert len(WORLD_ARCHETYPES)==64
    assert len(set(WORLD_ARCHETYPES))==64
    assert len(CONFLICTS)==16
    assert len(PERSPECTIVES)==len(TIMELINES)==len(STAGING)==8
    assert all("mario" not in name and "fallout" not in name and
               "minecraft" not in name for name in WORLD_ARCHETYPES)
    assert all("copyright" in bible(unrank("0")).originality_boundary
               or "unlicensed" in bible(unrank("0")).originality_boundary
               for _ in range(1))


def test_world_genome_axes_select_truly_different_original_narrative_structures():
    original=bible(unrank("0"))
    perspective=bible(edit("0",{"memory_reliability":1}))
    timeline=bible(edit("0",{"historical_drift":1}))
    staging=bible(edit("0",{"future_visibility":1}))
    world=bible(edit("0",{"world_seam_complexity":2}))
    conflict=bible(edit("0",{"moral_ambiguity":3}))
    assert original.perspective!=perspective.perspective
    assert original.timeline!=timeline.timeline
    assert original.staging!=staging.staging
    assert original.setting!=world.setting
    assert original.core_conflict!=conflict.core_conflict
    assert len({
        x.design_digest for x in (
            original,perspective,timeline,staging,world,conflict)
    })==6


def test_delayed_revelation_is_time_gated_by_real_play_not_plain_book_page():
    source=edit("0",{"revelation_delay":255})
    state=open_story(source)
    assert bible(source).delayed_revelation_steps==16
    choices=story_options(source,state)
    assert not choices["complete_chapter"]["available"]
    after=choose(source,choose(source,state,"investigate"),"investigate")
    assert after.evidence==2
    assert not after.revelations
    with pytest.raises(ValueError):
        choose(source,after,"complete_chapter")
    for _ in range(14):
        after=choose(source,after,"explore_elsewhere")
    assert after.world.player.base.turn==16
    assert "historical_record" in after.revelations
    assert story_options(source,after)["complete_chapter"]["available"]
    closed=choose(source,after,"complete_chapter")
    assert closed.chapters==1
    assert closed.world.player.base.turn==17


def test_original_story_ending_is_optional_and_world_continues_after_ending():
    source=unrank("0")
    choices=(
        "investigate","investigate","support_commune",
        "support_commune","complete_chapter","choose_aftermath",
        "explore_elsewhere","investigate",
    )
    ended=replay_story(source,choices)
    summary=story_report(source,ended)
    assert summary["ended_a_story"]
    assert not summary["ended_the_world"]
    assert summary["playable_after_story"]
    assert ended.endings==("communal_renewal",)
    assert ended.world.player.base.turn==len(choices)
    assert ended.story_digest==replay_story(source,choices).story_digest
    assert ended.scene_log==choices


def test_original_story_different_ethics_produce_actual_different_aftermath():
    source=unrank("0")
    civic=replay_story(source,(
        "investigate","investigate","support_commune",
        "support_commune","complete_chapter","choose_aftermath",
    ))
    nature=replay_story(source,(
        "investigate","investigate","support_wilderness",
        "support_wilderness","complete_chapter","choose_aftermath",
    ))
    balance=replay_story(source,(
        "investigate","investigate","support_wilderness",
        "support_commune","complete_chapter","choose_aftermath",
    ))
    assert civic.endings==("communal_renewal",)
    assert nature.endings==("rewilded_frontier",)
    assert balance.endings==("cooperative_balance",)
    assert len({x.story_digest for x in (civic,nature,balance)})==3
    assert all(x.world.player.base.turn==6 for x in (civic,nature,balance))


def test_evidence_can_be_preserved_or_concealed_with_persistent_consequences():
    source=unrank("0")
    original=choose(source,open_story(source),"investigate")
    assert original.evidence==1
    save=choose(source,original,"preserve_evidence")
    hide=choose(source,original,"conceal_evidence")
    assert save.reliability>original.reliability
    assert hide.reliability<original.reliability
    assert save.commitments==("preserve_evidence",)
    assert hide.commitments==("conceal_evidence",)
    assert save.story_digest!=hide.story_digest
    assert save.world.history_digest!=hide.world.history_digest


def test_unearned_story_decisions_cannot_mint_endings_or_reconstruction():
    world=unrank("0")
    player=open_story(world)
    for command in ("choose_aftermath","complete_chapter",
                    "reconstruct","negotiate","preserve_evidence"):
        with pytest.raises(ValueError):
            choose(world,player,command)
    with pytest.raises(ValueError):
        choose(world,player,"pretend_movie_scene")
    with pytest.raises(ValueError):
        replay_story(world,("no_real_story_action",))
    with pytest.raises(ValueError):
        replay_story(world,("investigate",)*97)


def test_story_reconstruction_needs_real_discovery_and_support():
    addr=unrank("0")
    game=replay_story(addr,(
        "investigate","investigate","support_commune",
    ))
    assert story_options(addr,game)["reconstruct"]["available"]
    moved=choose(addr,game,"reconstruct")
    assert "reconstruct" in moved.commitments
    assert moved.story_digest!=game.story_digest
    assert moved.world.player.base.turn==game.world.player.base.turn+1
