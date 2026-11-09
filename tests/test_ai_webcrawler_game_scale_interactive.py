"""End-to-end smoke for playable game-builder milestones.

Build and inspect actual archives and executable HTML generated from the
knowledge engine; regressions here guard delivered user functionality.
"""
from io import BytesIO
from zipfile import ZipFile
from hashlib import sha256
import json
import sqlite3

from skeleton.ai.webcrawler.game_knowledge_index import GameKnowledgeIndex
from skeleton.ai.webcrawler.game_scale_world import (
    generate_world_region,world_region_to_blueprint,
)
from skeleton.ai.webcrawler.game_playable_builder import build_playable_web_game
from skeleton.ai.webcrawler.game_scale_integration import build_enhanced_game
from skeleton.ai.webcrawler.game_scale_campaign import generate_game_campaign
from skeleton.ai.webcrawler.game_scale_campaign_hub import export_interactive_campaign
from skeleton.ai.webcrawler.game_scale_feedback import (
    decode_play_sessions,analyze_player_feedback,tune_game_from_feedback,
)
from skeleton.ai.webcrawler.game_builder_cli import run


def test_actual_top_down_world_has_connected_goal_and_moving_enemies():
    region=generate_world_region("Crystal Vault",rooms=6,seed=17,columns=3)
    blueprint=world_region_to_blueprint(
        region,title="Crystal Vault",seed=17,pickups=7,enemies=2,
    )
    assert blueprint.genre=="exploration"
    assert sum(row.count("P") for row in blueprint.grid)==1
    assert sum(row.count("G") for row in blueprint.grid)==1
    assert sum(row.count("C") for row in blueprint.grid)>0
    output=build_playable_web_game(blueprint)
    assert 'scene.genre==="exploration"' in output.html
    assert "const vertical=Number(down())-Number(up())" in output.html
    assert "p.alive&&dist<TILE*8" in output.html
    assert output.scene["entities"]
    assert len(output.fingerprint)==64


def test_enhanced_archive_contains_real_editor_art_music_and_actions():
    region=generate_world_region("Hidden Forge",rooms=4,seed=19)
    blueprint=world_region_to_blueprint(
        region,title="Hidden Forge",seed=19,pickups=3,enemies=2,
    )
    project=build_enhanced_game(blueprint,theme="cyber")
    with ZipFile(BytesIO(project.archive)) as archive:
        names=set(archive.namelist())
        assert {"index.html","studio.html","scene.json",
                "build-report.json","assets/theme.wav",
                "assets/hero.svg","assets/hit.wav"}<=names
        html=archive.read("index.html").decode()
        studio=archive.read("studio.html").decode()
        assert 'data-button="shoot"' in html
        assert 'data-button="heal"' in html
        assert 'data-button="shop"' in html
        assert "function updateAdvancedCombat(dt)" in html
        assert "function exportGameTelemetry()" in html
        assert "function buildHtml()" in studio
        assert 'sandbox="allow-scripts"' in studio
        assert len(archive.read("assets/theme.wav"))>1000


def test_connected_campaign_has_real_unlocks_and_save_capability():
    index=GameKnowledgeIndex(sqlite3.connect(":memory:"))
    campaign=generate_game_campaign(
        index,title="Arc of the Source",genre="platformer",
        seed=19,chapters=3,
    )
    package=export_interactive_campaign(campaign)
    with ZipFile(BytesIO(package)) as archive:
        names=set(archive.namelist())
        assert {"index.html","campaign.json","README.md",
                "levels/level-001.html","levels/level-002.html",
                "levels/level-003.html"}<=names
        launcher=archive.read("index.html").decode()
        playable=archive.read("levels/level-001.html").decode()
        assert "function finish(id)" in launcher
        assert "function validProgress(data)" in launcher
        assert 'skeleton.game.campaign.skills.v1' in launcher
        assert 'skeleton.game.campaign.completed.v1' in playable
        assert 'window.parent.postMessage' in playable
        assert "progress.xp+=ch.reward" in launcher


def test_play_feedback_is_tied_to_real_blueprint_and_rebuilds_safely():
    region=generate_world_region("Feedback Map",rooms=3,seed=7)
    blueprint=world_region_to_blueprint(region,title="Feedback Map",seed=7)
    fixture={
        "schema":"skeleton.original_game.telemetry.v1",
        "blueprint":blueprint.fingerprint,
        "events":[
            {"event":"spawn","second":0,"x":32,"y":32},
            {"event":"damage","second":2,"x":100,"y":120},
            {"event":"retry","second":3,"x":32,"y":32},
            {"event":"damage","second":6,"x":112,"y":128},
            {"event":"retry","second":7,"x":32,"y":32},
            {"event":"victory","second":12,"x":220,"y":180},
        ],
    }
    source,events=decode_play_sessions(json.dumps(fixture).encode())
    feedback=analyze_player_feedback(source,events)
    tuning=tune_game_from_feedback(blueprint,feedback)
    assert feedback.death_hotspots
    assert feedback.completion_rate>0
    assert tuning.new_blueprint.fingerprint!=blueprint.fingerprint
    assert tuning.new_blueprint.physics_dict()["move_speed"]>0
    assert build_playable_web_game(tuning.new_blueprint).html


def test_cli_builds_exploration_game_with_actual_world_zip(tmp_path):
    target=tmp_path/"world.zip"
    assert run([
        "--title","The Great Labyrinth","--genre","exploration",
        "--engine","web","--world-rooms","4",
        "--output",str(target),"--approve",
    ])==0
    with ZipFile(target) as archive:
        assert {"index.html","scene.json","README.md"}<=set(archive.namelist())
        scene=json.loads(archive.read("scene.json"))
        assert scene["genre"]=="exploration"
        assert any(e["type"]=="goal" for e in scene["entities"])
