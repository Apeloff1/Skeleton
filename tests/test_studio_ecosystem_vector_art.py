from copy import deepcopy
from hashlib import sha256
import xml.etree.ElementTree as ET
import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_vector_art import render_environment_svg, vector_art_receipt
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

@pytest.mark.parametrize("project",[
    "studio_aerial_traversal_amber_highlands",
    "studio_arena_fighting_glacial_fjord",
])
def test_source_derived_svg_is_reproducible_original_media(project):
    docs=read_blueprint(project)
    data=render_environment_svg(docs)
    root=ET.fromstring(data)
    assert root.attrib["viewBox"]=="0 0 1280 720"
    assert len(root.findall(".//{http://www.w3.org/2000/svg}polygon"))>=7
    assert render_environment_svg(docs)==data
    receipt=vector_art_receipt(docs)
    assert receipt["svg_sha256"]==sha256(data).hexdigest()
    assert receipt["original_asset_rendered"]
    assert receipt["native_world_rendered"] is False
    assert receipt["release_certified"] is False

def test_invalid_colour_refused_before_asset_generation():
    docs=deepcopy(read_blueprint("studio_arena_fighting_glacial_fjord"))
    docs["visual"]["art_direction"]["palette"][0]="url(javascript:alert(1))"
    with pytest.raises(StudioQuestError):
        render_environment_svg(docs)
