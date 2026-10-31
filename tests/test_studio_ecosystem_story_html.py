"""Offline HTML director source binding and script-injection boundaries."""
import json
import re
from copy import deepcopy
from hashlib import sha256
import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_story_html import (
    story_source,render_story_html,story_html_receipt,
)

@pytest.mark.parametrize("pid",[
    "studio_aerial_traversal_amber_highlands",
    "studio_puzzle_expedition_copper_mesa",
    "studio_arena_fighting_glacial_fjord",
])
def test_authored_quest_actions_run_in_offline_browser(pid):
    docs=read_blueprint(pid)
    source=story_source(docs)
    html=render_story_html(docs)
    assert len(source["stages"])==3
    assert len(source["endings"])==3
    assert all(stage["alternatives"] for stage in source["stages"])
    assert b"function act(" in html and b"addEventListener" in html
    assert b"localStorage" not in html and b"fetch(" not in html
    assert html==render_story_html(docs)
    assert story_html_receipt(docs)["html_sha256"]==sha256(html).hexdigest()

def test_authored_text_cannot_escape_inert_json_script():
    docs=deepcopy(read_blueprint("studio_arena_fighting_glacial_fjord"))
    docs["quest"]["stage_graph"][0]["alternatives"][0]="</script><script>alert(1)</script>"
    html=render_story_html(docs).decode("utf-8")
    captured=re.search(r"<script type='application/json' id='studio-source'>(.*?)</script>",
                       html,re.S).group(1)
    assert "</script>" not in captured
    assert json.loads(captured)["stages"][0]["alternatives"][0]=="</script><script>alert(1)</script>"
    assert "alert(1)" not in html.replace(captured,"")

def test_story_csp_uses_content_hashes_not_permissive_inline_scripts():
    docs=read_blueprint("studio_aerial_traversal_amber_highlands")
    html=render_story_html(docs)
    assert b"'unsafe-inline'" not in html
    assert html.count(b"'sha256-")>=3
    assert b"object-src 'none'" in html
    assert b"addEventListener" in html
