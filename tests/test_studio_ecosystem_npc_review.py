import json
import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_npc_patrol import cast_patrols
from skeleton.ai.game_builder.studio_ecosystem_walk_replay import start_walk
from skeleton.ai.game_builder.studio_ecosystem_npc_review import review_npc_dialogue_log
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

def _body(docs,contacts,events=None):
    session=start_walk(docs,authorized=True)
    return json.dumps({"schema":"skeleton.game_builder.offline_npc_contacts.v1",
                       "project_id":session.project_id,
                       "source_digest":session.source_digest,
                       "events":events or [],"contacts":contacts,
                       "release_certified":False}).encode()

def test_empty_valid_log_and_unknown_talk_refusal():
    docs=read_blueprint("studio_arena_fighting_glacial_fjord")
    receipt=review_npc_dialogue_log(docs,_body(docs,[]),authorized=True)
    assert receipt["local_contacts_verified"]==0
    assert not receipt["real_world_witness_claim_verified"]
    with pytest.raises(StudioQuestError):
        review_npc_dialogue_log(
            docs,_body(docs,[{"id":"forged_witness","event_cursor":0}]),
            authorized=True)

def test_npc_dialogue_log_does_not_claim_release():
    docs=read_blueprint("studio_aerial_traversal_amber_highlands")
    npc=cast_patrols(docs)["actors"][0]
    source=start_walk(docs,authorized=True)
    assert npc["knows"] and source.source_digest
    with pytest.raises(PermissionError):
        review_npc_dialogue_log(docs,_body(docs,[]),authorized=False)
