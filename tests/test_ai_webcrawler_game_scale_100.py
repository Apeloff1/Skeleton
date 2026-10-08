"""End-to-end checks for actual 100-capability game construction and 10x output."""
from __future__ import annotations
from io import BytesIO
from zipfile import ZipFile
import json
import sqlite3
import wave

import pytest

from skeleton.ai.webcrawler.game_scale_catalog import (
    MILESTONES, game_milestone_by_number,grouped_game_milestones,
)
from skeleton.ai.webcrawler.game_scale_world import generate_world_region
from skeleton.ai.webcrawler.game_scale_npc_ai import (
    npc_astar,npc_chase,npc_line_of_sight,
)
from skeleton.ai.webcrawler.game_scale_combat import (
    configure_weapon,Fighter,melee_targets,fire_projectile,
    advance_projectiles,apply_combat_damage,
)
from skeleton.ai.webcrawler.game_scale_economy import (
    Inventory,define_game_item,inventory_add,inventory_remove,
    simulate_game_economy,
)
from skeleton.ai.webcrawler.game_scale_story import (
    Objective,QuestProgress,StoryState,define_quest,
    apply_quest_event,complete_quest,story_save_slot,restore_story_slot,
)
from skeleton.ai.webcrawler.game_scale_assets import (
    generate_game_palette,procedural_heightmap,
    procedural_sprite,sprite_to_svg,synthesize_game_effect,
)
from skeleton.ai.webcrawler.game_scale_balancing import (
    evaluate_game_balance,simulate_input_latency,
)
from skeleton.ai.webcrawler.game_scale_editor import (
    paint_scene_tile,open_editor_history,record_editor_edit,
    undo_scene_edit,redo_scene_edit,
)
from skeleton.ai.webcrawler.game_scale_campaign import (
    generate_game_campaign,export_campaign_archive,
    available_campaign_chapters,HeroProgress,complete_campaign_chapter,
    encode_campaign_save,decode_campaign_save,
)
from skeleton.ai.webcrawler.game_scale_mass_production import produce_game_portfolio
from skeleton.ai.webcrawler.game_scale_integration import build_enhanced_game
from skeleton.ai.webcrawler.game_scale_studio import generate_level_studio
from skeleton.ai.webcrawler.game_knowledge_index import GameKnowledgeIndex
from skeleton.ai.webcrawler.game_knowledge_design import (
    propose_game_blueprint,populate_game_level,find_level_route,
)
from skeleton.ai.webcrawler.game_builder_cli import run


def index():
    return GameKnowledgeIndex(sqlite3.connect(":memory:"))


def blueprint():
    return populate_game_level(propose_game_blueprint(
        index(),title="Moon Quest",genre="platformer",engine="web",seed=17,
    ))


def test_registry_resolves_exactly_100_real_local_functions():
    assert len(MILESTONES)==100
    assert len(grouped_game_milestones())==10
    assert all(len(items)==10 for _,items in grouped_game_milestones())
    names=set()
    for rank in range(1,101):
        entry=MILESTONES[rank-1]
        operation=game_milestone_by_number(rank)
        assert callable(operation)
        assert operation.__name__==entry.operation
        assert operation.__module__.endswith(entry.module[1:])
        assert entry.operation not in names
        names.add(entry.operation)
    with pytest.raises(ValueError):
        game_milestone_by_number(101)


def test_connected_world_generation_and_actual_npc_navigation():
    region=generate_world_region("Ancient Forge",rooms=6,seed=123)
    assert sum(row.count("P") for row in region.tiles)==1
    assert sum(row.count("G") for row in region.tiles)==1
    assert len(region.connections)>=5
    path=find_level_route(region.tiles)
    assert len(path)>10
    route=npc_astar(region.tiles,region.spawn,region.exit)
    assert route[0]==region.spawn and route[-1]==region.exit
    chase=npc_chase(region.tiles,region.spawn,region.exit,sight_radius=100)
    assert chase.action=="chase"


def test_real_weapon_projectile_armor_and_inventory_flow():
    sword=configure_weapon("Steel Cut",damage=12,reach=3,cooldown=.3)
    staff=configure_weapon("Ember",damage=7,reach=30,cooldown=.6,
                           speed=30,projectile=True)
    hero=Fighter("hero",0,0,100,100)
    enemy=Fighter("enemy",2,0,25,25,armor=2)
    assert melee_targets(hero,(enemy,),sword,facing=(1,0))==(enemy,)
    hurt,amount=apply_combat_damage(enemy,sword.damage)
    assert amount==10 and hurt.health==15
    fired=fire_projectile(hero,staff,direction=(1,0))
    moved=advance_projectiles((fired,),delta=.1,bounds=(-10,-10,50,50))
    assert len(moved)==1 and moved[0].x==3.
    wood=define_game_item("wood",category="material",value=3,weight=2)
    stock=inventory_add(Inventory(),wood,3,catalog={"wood":wood})
    assert dict(stock.stacks)=={"wood":3}
    assert inventory_remove(stock,"wood",2).stacks==( ("wood",1), )
    assert simulate_game_economy(100,earned=25,spent=50)==(75,0)


def test_quest_progression_and_persistent_story_decisions():
    quest=define_quest("bridge","Repair Bridge",
        (Objective("wood","collect","wood",3),),reward=45)
    progress=apply_quest_event(
        quest,QuestProgress("bridge",state="active"),
        kind="collect",target="wood",quantity=3,
    )
    completed,coins=complete_quest(quest,progress)
    assert completed.state=="complete" and coins==45
    story=StoryState(flags=frozenset({"accepted"}),visited=("start",))
    assert restore_story_slot(story_save_slot(story))==story


def test_synthesized_art_and_audio_are_real_binary_assets():
    colors=generate_game_palette(19,theme="cyber")
    sprite=procedural_sprite(19,kind="hero",palette=colors)
    svg=sprite_to_svg(sprite)
    assert svg.startswith("<svg") and svg.count("<rect")>20
    terrain=procedural_heightmap(24,24,seed=11)
    assert len(terrain)==24 and all(0<=h<=1 for row in terrain for h in row)
    sound=synthesize_game_effect("pickup")
    with wave.open(BytesIO(sound),"rb") as stream:
        assert stream.getnframes()>1000 and stream.getnchannels()==1


def test_balancing_and_scene_editor_modify_really_playable_world():
    game=blueprint()
    report=evaluate_game_balance(game)
    assert report.route_tiles>0 and report.estimated_seconds>0
    failure,latency=simulate_input_latency(game,runs=20,seed=2)
    assert 0<=failure<=1 and latency>=0
    # Add a collectible on a safe open route tile: editor keeps route open.
    chosen=next((x,y) for y,row in enumerate(game.grid)
                for x,tile in enumerate(row) if tile==".")
    edited=paint_scene_tile(game,*chosen,"C")
    assert edited.grid[chosen[1]][chosen[0]]=="C"
    history=open_editor_history(game)
    history=record_editor_edit(history,edited)
    history,back=undo_scene_edit(history)
    assert back.grid==game.grid
    history,again=redo_scene_edit(history)
    assert again.grid==edited.grid


def test_campaign_has_playable_chapters_and_real_progress_saves():
    campaign=generate_game_campaign(index(),title="Moon Odyssey",
        genre="platformer",chapters=3)
    assert len(campaign.chapters)==3
    ready=available_campaign_chapters(campaign,HeroProgress())
    assert len(ready)==1
    hero=complete_campaign_chapter(campaign,HeroProgress(),ready[0].chapter_id)
    assert hero.experience>0 and len(hero.cleared)==1
    assert decode_campaign_save(campaign,encode_campaign_save(campaign,hero))==hero
    archive=export_campaign_archive(campaign)
    with ZipFile(BytesIO(archive)) as z:
        assert "index.html" in z.namelist()
        assert len([x for x in z.namelist() if x.endswith(".html")])==4


def test_enhanced_game_zip_contains_real_studio_and_original_assets():
    game=blueprint()
    result=build_enhanced_game(game,theme="forest")
    assert result.balancing.route_tiles>0
    with ZipFile(BytesIO(result.archive)) as z:
        names=set(z.namelist())
        assert "index.html" in names and "studio.html" in names
        assert "assets/hero.svg" in names and "assets/pickup.wav" in names
        assert "assets/theme.wav" in names and "build-report.json" in names
        assert "pointerdown" in z.read("studio.html").decode()
        assert "Play Preview" in z.read("studio.html").decode()
        assert "const sounds=" in z.read("index.html").decode()


def test_tenfold_batch_produces_distinct_playable_web_games():
    output=produce_game_portfolio(
        index(),title="Hundred Forge",count=4,seed=100,
        authorized=True,human_approved=True,
    )
    assert len(output.games)==4
    assert len({game.original_sha256 for game in output.games})==4
    assert len({game.genre for game in output.games})==4
    with ZipFile(BytesIO(output.archive)) as z:
        assert "index.html" in z.namelist()
        assert "portfolio.json" in z.namelist()
        games=[n for n in z.namelist() if n.startswith("games/")]
        assert len(games)==4
        assert all(b"requestAnimationFrame" in z.read(n) for n in games)


def test_cli_exports_user_ready_extended_and_batch_builds(tmp_path):
    enriched=tmp_path/"enhanced.zip"
    assert run(["--title","Game Studio","--genre","platformer",
        "--output",str(enriched),"--approve","--enhanced","--theme","forest"])==0
    with ZipFile(enriched) as z:
        assert "studio.html" in z.namelist()
    batch=tmp_path/"portfolio.zip"
    assert run(["--title","Game Portfolio","--genre","platformer",
        "--output",str(batch),"--approve","--batch-games","3"])==0
    with ZipFile(batch) as z:
        assert len([x for x in z.namelist() if x.startswith("games/")])==3
