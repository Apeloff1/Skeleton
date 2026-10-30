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


def test_actual_reachable_original_npc_contact_is_independently_verified():
    from collections import deque
    from skeleton.ai.game_builder.studio_ecosystem_walkable import playable_world_source
    from skeleton.ai.game_builder.studio_ecosystem_walk_replay import DIRECTIONS
    docs=read_blueprint("studio_arena_fighting_glacial_fjord")
    actor=cast_patrols(docs)["actors"][0]
    world=playable_world_source(docs)
    rows=world["maps"][0]
    start=(1,1,0)
    queue=deque([start])
    seen={start:[]}
    found=None
    while queue:
        x,y,phase=queue.popleft()
        nx,ny=actor["patrol_by_stage"][0][phase]
        if abs(x-nx)+abs(y-ny)<=1:
            found=seen[(x,y,phase)]
            break
        for direction,(dx,dy) in DIRECTIONS.items():
            px,py=x+dx,y+dy
            state=(px,py,1-phase)
            if (0<=px<world["width"] and 0<=py<world["height"]
                    and rows[py][px]=="." and state not in seen):
                seen[state]=seen[(x,y,phase)]+[["move",direction]]
                queue.append(state)
    assert found is not None
    body=_body(docs,[{"id":actor["id"],"event_cursor":len(found)}],found)
    reviewed=review_npc_dialogue_log(docs,body,authorized=True)
    assert reviewed["local_contacts_verified"]==1
    assert reviewed["contacts"][0]["authored_knowledge"]==actor["knows"]
