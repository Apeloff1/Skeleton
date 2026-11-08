from copy import deepcopy
import json
import re
import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_walkable import (
    _reachable,playable_world_source,render_playable_world_html,
)

@pytest.mark.parametrize("project",[
 "studio_aerial_traversal_amber_highlands",
 "studio_puzzle_expedition_copper_mesa",
 "studio_arena_fighting_glacial_fjord",
])
def test_all_original_source_families_produce_real_walkable_scene_maps(project):
    docs=read_blueprint(project)
    source=playable_world_source(docs)
    assert len(source["maps"])==len(source["stages"])==3
    assert all(_reachable(rows) for rows in source["maps"])
    assert all(rows[1][1]=="." for rows in source["maps"])
    assert all(rows[8][14]=="." for rows in source["maps"])
    html=render_playable_world_html(docs)
    assert b"<canvas" in html and b"function move" in html and b"function choose" in html
    assert b"fetch(" not in html and b"localStorage" not in html
    assert html==render_playable_world_html(docs)
    assert source["target_genre_runtime_implemented"] is False

def test_malicious_choice_cannot_escape_inert_json_into_html():
    docs=deepcopy(read_blueprint("studio_arena_fighting_glacial_fjord"))
    docs["quest"]["stage_graph"][0]["alternatives"][0]="</script><script>evil()</script>"
    html=render_playable_world_html(docs).decode("utf-8")
    data=re.search(r"<script type='application/json' id='world-source'>(.*?)</script>",html,re.S)
    assert data is not None
    assert "</script>" not in data.group(1)
    assert json.loads(data.group(1))["stages"][0]["alternatives"][0]=="</script><script>evil()</script>"

def test_walkable_browser_has_actual_bfs_hint_without_teleportation():
    docs=read_blueprint("studio_aerial_traversal_amber_highlands")
    html=render_playable_world_html(docs)
    assert b"function hint()" in html
    assert b"Shortest reachable route" in html
    assert b'id=\'navigation-hint\'' in html
    assert b"player.x=x;player.y=y;steps++;draw();" in html

def test_walkable_browser_renders_real_hazards_and_source_health():
    docs=read_blueprint("studio_arena_fighting_glacial_fjord")
    data=render_playable_world_html(docs)
    assert b"hazards_by_stage" in data
    assert b"playerHealth--" in data
    assert b"Character defeated by hazard contact" in data

def test_walkable_csp_hashes_rendered_program_and_source_without_unsafe_inline():
    docs=read_blueprint("studio_arena_fighting_glacial_fjord")
    html=render_playable_world_html(docs)
    assert b"'unsafe-inline'" not in html
    assert html.count(b"'sha256-")>=3
    assert b"form-action 'none'" in html

def test_canvas_renders_original_actor_patrol_and_safe_dialogue():
    docs=read_blueprint("studio_aerial_traversal_amber_highlands")
    html=render_playable_world_html(docs)
    assert b'"actors":' in html
    assert b"Talk to " in html
    assert b"actor.knows" in html
    assert b"npc-dialogue" in html
    assert b"Rika Morrow" in html
