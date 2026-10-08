"""Working game-knowledge acquisition -> indexed retrieval -> playable builds.

These integration tests exercise the actual source corpus and project artifacts,
rather than treating an architecture document as a working game builder.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
from hashlib import sha256
import json
import sqlite3

import pytest

from skeleton.ai.webcrawler.core import FetchResponse, extract_document, CrawlEngine, CrawlPolicy
from skeleton.ai.webcrawler.game_knowledge_acquisition import (
    extract_game_sections, extract_engine_symbols, extract_game_parameters,
    official_game_documentation, enqueue_official_game_docs,
)
from skeleton.ai.webcrawler.game_knowledge_index import GameKnowledgeIndex
from skeleton.ai.webcrawler.game_knowledge_design import (
    propose_game_blueprint, populate_game_level,
    analyze_level_playability, find_level_route, estimate_jump_reach,
)
from skeleton.ai.webcrawler.game_playable_builder import (
    build_playable_web_game, export_playable_game_archive,
)
from skeleton.ai.webcrawler.game_godot_export import export_godot_game_archive
from skeleton.ai.webcrawler.game_builder_knowledge_runtime import KnowledgeDrivenGameBuilder
from skeleton.ai.webcrawler.game_builder_cli import import_research_captures, run


def doc(host="alpha.example",text=None):
    content=text or (
        "CharacterBody2D game movement and jump buffering depend on collision. "
        "Use move_and_slide with a 60 fps physics loop. "
        "A platforming jump trajectory requires gravity and velocity. "
    )*10
    url="https://"+host+"/game-dev"
    return extract_document(
        FetchResponse(url,200,{"content-type":"text/plain"},
                      content.encode(),1700000000),
        url,
    )


def test_acquired_game_docs_extract_real_api_and_tuning_spans():
    source=doc()
    spans=extract_game_sections(source)
    assert spans
    assert all(source.text[p.start:p.end]==p.text for p in spans)
    assert all(p.content_hash==source.content_hash for p in spans)
    apis=extract_engine_symbols(spans)
    assert any(x.symbol=="CharacterBody2D" for x in apis)
    tuning=extract_game_parameters(spans)
    assert any(x.value==60 and x.unit=="fps" for x in tuning)


def test_game_knowledge_index_supports_retrieval_history_and_revision_diff():
    index=GameKnowledgeIndex(sqlite3.connect(":memory:"))
    original=doc()
    count=index.ingest_document("source-1",original,engine="godot",
                                year=2026,authorized=True)
    assert count>=1
    hits=index.search("jump buffering game movement")
    assert hits and hits[0].source_id=="source-1"
    assert index.search_engine_api("CharacterBody2D")
    assert index.search_mechanic("jump")
    context=index.assemble_game_context("jump collision",engine="godot")
    assert "UNTRUSTED" in context and original.content_hash in context
    revised=doc(text="Godot movement collision and jump controller tuning. "*12)
    old,new=index.replace_source_revision(
        "source-1",revised,engine="godot",authorized=True,
    )
    assert old==original.content_hash and new==revised.content_hash
    assert len(index.source_history("source-1"))==2
    removed,added=index.compare_source_revisions("source-1",old,new)
    assert removed and added
    assert all(hit.content_hash==new for hit in index.search("jump controller"))
    assert index.missing_knowledge(("camera","jump"),min_sources=2)[0].coverage<=.5


def test_identical_mirrors_dont_satisfy_independence_coverage():
    index=GameKnowledgeIndex(sqlite3.connect(":memory:"))
    first=doc(host="first.example")
    mirror=doc(host="mirror.example")
    index.ingest_document("first",first,engine="web",authorized=True)
    index.ingest_document("mirror",mirror,engine="web",authorized=True)
    gap=index.missing_knowledge(("jump",),min_sources=2)[0]
    assert gap.matching_sources==1
    assert gap.coverage==.5
    assert len(index.source_history("mirror"))==1


def test_design_produces_actual_original_traversable_level_and_reachable_jump():
    builder=KnowledgeDrivenGameBuilder(sqlite3.connect(":memory:"))
    builder.ingest_captured_documents((doc(),),engine="web",authorized=True)
    bp=propose_game_blueprint(
        builder.knowledge,title="Moon Hop",genre="platformer",
        engine="web",seed=17,
    )
    designed=populate_game_level(bp,pickups=6,enemies=2)
    analysis=analyze_level_playability(designed)
    assert analysis.playable and analysis.shortest_route>0
    assert analysis.collectibles>=4
    assert find_level_route(designed.grid)[0]==(1,designed.height-2)
    travel,apex=estimate_jump_reach(
        speed=designed.physics_dict()["move_speed"],
        jump_speed=designed.physics_dict()["jump_speed"],
        gravity=designed.physics_dict()["gravity"],
    )
    assert travel>=5 and apex>=4
    assert designed.fingerprint!=bp.fingerprint


def test_exported_web_project_contains_actual_playable_input_physics_and_ai():
    builder=KnowledgeDrivenGameBuilder(sqlite3.connect(":memory:"))
    build=builder.build_game(
        title="Original Jump Game",genre="platformer",authorized=True,
        human_approved=True,engine="web",seed=23,
    )
    assert build.metrics.playable
    html=build.playable.html
    for real_feature in (
        "requestAnimationFrame(frame)","physicsStep(1/60)",
        "moveAxis(", "updateEnemies(", "updateGameState(",
        "updateCamera(", "keydown", "pointerdown", "loseLife(",
        "function draw()", "KeyJ",
    ):
        assert real_feature in html
    with ZipFile(BytesIO(build.archive)) as archive:
        assert set(archive.namelist())=={"index.html","scene.json","README.md"}
        assert archive.read("index.html").decode()==html
        game=json.loads(archive.read("scene.json"))
        assert game["blueprint"]==build.blueprint.fingerprint
        assert game["entities"]
        assert any(e["type"]=="goal" for e in game["entities"])


def test_puzzle_level_uses_real_collectible_gated_goal():
    builder=KnowledgeDrivenGameBuilder(sqlite3.connect(":memory:"))
    result=builder.build_game(
        title="Switch Puzzle",genre="puzzle",authorized=True,
        human_approved=True,engine="web",
    )
    assert 'scene.genre==="puzzle"' in result.playable.html
    assert "state.pickups.some(item=>item.active)" in result.playable.html
    assert result.metrics.collectibles>0


def test_godot_archive_contains_native_scene_player_and_game_logic():
    builder=KnowledgeDrivenGameBuilder(sqlite3.connect(":memory:"))
    build=builder.build_game(
        title="Native Jump",genre="platformer",engine="godot",
        authorized=True,human_approved=True,seed=19,
    )
    with ZipFile(BytesIO(build.archive)) as archive:
        names=set(archive.namelist())
        assert {"project.godot","main.tscn","main.gd","player.gd",
                "level.json","README.md"}==names
        main=archive.read("main.gd").decode()
        player=archive.read("player.gd").decode()
        assert "StaticBody2D.new()" in main
        assert "InputMap.add_action" in main
        assert "move_and_slide()" in player
        assert "CharacterBody2D" in player
        level=json.loads(archive.read("level.json"))
        assert level["blueprint"]==build.blueprint.fingerprint
        assert level["collision"]
        assert level["entities"]


def test_game_builder_refuses_unapproved_or_unsupported_target():
    builder=KnowledgeDrivenGameBuilder(sqlite3.connect(":memory:"))
    with pytest.raises(PermissionError):
        builder.build_game(title="No",genre="platformer",engine="web",
                           authorized=True,human_approved=False)
    with pytest.raises(ValueError,match="exporter"):
        builder.build_game(title="No",genre="platformer",engine="unreal",
                           authorized=True,human_approved=True)


def test_official_docs_are_real_governed_frontier_seeds():
    godot=official_game_documentation("godot")
    unity=official_game_documentation("unity")
    assert godot and unity
    assert any("godotengine.org" in s.url for s in godot)
    assert any("docs.unity.com" in s.url for s in unity)
    class NoFetch:
        def fetch(self,*args,**kwargs):
            raise AssertionError("never fetch during enqueue")
    engine=CrawlEngine(NoFetch(),policy=CrawlPolicy(max_depth=0))
    queued=enqueue_official_game_docs(engine,engine="godot")
    assert queued and all("godotengine.org" in url for url in queued)


def test_cli_imports_local_research_without_claiming_real_http_provenance(tmp_path):
    path=tmp_path/"source.json"
    path.write_text(json.dumps([{
        "url":"https://game-docs.example/article",
        "text":"Jump buffering and collision in original game systems. "*10,
    }]))
    sources=import_research_captures(path)
    assert sources[0].provenance["schema"]=="skeleton.ai.crawl.local_capture.v1"
    result=tmp_path/"produced.zip"
    assert run([
        "--title","Test Project","--genre","platformer",
        "--engine","web","--sources",str(path),
        "--output",str(result),"--approve",
    ])==0
    assert result.exists()
    with ZipFile(result) as archive:
        assert "index.html" in archive.namelist()


def test_research_dependencies_affect_game_compiler_only_after_two_distinct_sources():
    index=GameKnowledgeIndex(sqlite3.connect(":memory:"))
    a=doc("first.example",text=(
        "The game design explicitly states dash requires combat. "
        "Platformer movement and collision are essential. "
    )*12)
    b=doc("second.example",text=(
        "In this independent game system guide dash requires combat. "
        "A platformer dash needs movement and collision. "
    )*12)
    index.ingest_document("a",a,engine="web",authorized=True)
    assert "dash" not in index.confirmed_mechanic_dependencies()
    index.ingest_document("b",b,engine="web",authorized=True)
    deps=index.confirmed_mechanic_dependencies()
    assert "combat" in deps["dash"]
    blueprint=propose_game_blueprint(
        index,title="Research-Driven Dash",genre="platformer",
        engine="web",seed=4,
    )
    assert "dash" in blueprint.mechanics
    assert blueprint.mechanics.index("combat") < blueprint.mechanics.index("dash")
    html=build_playable_web_game(blueprint).html
    assert 'scene.mechanics.includes("dash")' in html
    assert 'scene.mechanics.includes("double_jump")' in html


def test_knowledge_index_fts_replays_after_reopening_on_disk(tmp_path):
    connection=sqlite3.connect(tmp_path/"facts.db")
    index=GameKnowledgeIndex(connection)
    index.ingest_document("source",doc(),engine="godot",authorized=True)
    original=index.search("CharacterBody2D")
    connection.close()
    reopened=sqlite3.connect(tmp_path/"facts.db")
    index2=GameKnowledgeIndex(reopened)
    assert index2.search("CharacterBody2D")==original
    reopened.close()
