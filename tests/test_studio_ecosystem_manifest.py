from copy import deepcopy
import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_manifest import source_manifest,verify_source_manifest
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

@pytest.mark.parametrize("pid",[
 "studio_aerial_traversal_amber_highlands",
 "studio_arena_fighting_glacial_fjord",
])
def test_content_addressed_eight_section_identity(pid):
    docs=read_blueprint(pid)
    manifest=source_manifest(docs)
    assert len(manifest["sections"])==8
    assert len(manifest["source_chain_sha256"])==64
    verify_source_manifest(manifest,docs)
    tampered=deepcopy(docs)
    tampered["visual"]["art_direction"]["palette"][0]="#FFFFFF"
    with pytest.raises(StudioQuestError):
        verify_source_manifest(manifest,tampered)
