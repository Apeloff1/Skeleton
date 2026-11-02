import json
from copy import deepcopy
import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_story_html import story_source
from skeleton.ai.game_builder.studio_ecosystem_story_review import (inspect_browser_story_receipt, preview_browser_story_choice)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

def _receipt(docs,actions):
    program=story_source(docs)
    return {"schema":"skeleton.game_builder.offline_story_choices.v1",
            "project_id":program["project_id"],"source_digest":program["source_digest"],
            "choices":actions,"external_evidence_verified":False,
            "native_genre_runtime_verified":False,"release_certified":False}

@pytest.mark.parametrize("pid",["studio_aerial_traversal_amber_highlands",
                               "studio_arena_fighting_glacial_fjord"])
def test_verified_browser_transcript_replays_actual_source(pid):
    docs=read_blueprint(pid)
    stage=story_source(docs)["stages"][0]
    payload=_receipt(docs,[[stage["id"],stage["alternatives"][0]]])
    result=inspect_browser_story_receipt(
        json.dumps(payload).encode(),docs,authorized=True)
    assert result["completed_stages"]==[stage["id"]]
    assert result["replayed_from_authoritative_source"]
    assert not result["release_certified"]

def test_browser_cannot_forge_progress_or_source_and_duplicate_json_is_refused():
    docs=read_blueprint("studio_arena_fighting_glacial_fjord")
    bad=_receipt(docs,[["ratify","residents_vote"]])
    with pytest.raises(StudioQuestError):
        inspect_browser_story_receipt(json.dumps(bad).encode(),docs,authorized=True)
    bad=_receipt(docs,[])
    bad["release_certified"]=True
    with pytest.raises(StudioQuestError):
        inspect_browser_story_receipt(json.dumps(bad).encode(),docs,authorized=True)
    with pytest.raises(StudioQuestError):
        inspect_browser_story_receipt(b'{"schema":1,"schema":2}',docs,authorized=True)


@pytest.mark.parametrize("pid", [
    "studio_aerial_traversal_amber_highlands",
    "studio_arena_fighting_glacial_fjord",
])
def test_choice_preview_is_canonical_noncommitting_and_replayable(pid):
    from skeleton.ai.game_builder.studio_ecosystem_quest import (
        replay_quest, step_quest, quest_progress,
    )
    docs = read_blueprint(pid)
    stage = story_source(docs)["stages"][0]
    raw = json.dumps(_receipt(docs, [])).encode()
    choice = stage["alternatives"][0]
    result = preview_browser_story_choice(
        raw, docs, stage=stage["id"], alternative=choice, authorized=True)
    base = replay_quest(docs, [], authorized=True)
    candidate = step_quest(base, docs, stage=stage["id"],
                           alternative=choice, authorized=True)
    progress = quest_progress(candidate, docs)
    assert result["base_session_digest"] == base.digest
    assert result["candidate_session_digest"] == candidate.digest
    assert result["unmet_ending_predicates"] == progress["unmet_ending_predicates"]
    assert result["baseline_session_unchanged"] is True
    assert result["release_certified"] is False
    assert replay_quest(docs, [], authorized=True).digest == base.digest


def test_choice_preview_rejects_invalid_action_stale_source_and_authority():
    docs = read_blueprint("studio_arena_fighting_glacial_fjord")
    raw = json.dumps(_receipt(docs, [])).encode()
    stage = story_source(docs)["stages"][0]
    with pytest.raises(StudioQuestError):
        preview_browser_story_choice(raw, docs, stage=stage["id"],
                                     alternative="unwritten-action", authorized=True)
    with pytest.raises(StudioQuestError):
        preview_browser_story_choice(raw, docs, stage=True,
                                     alternative=stage["alternatives"][0], authorized=True)
    with pytest.raises(PermissionError):
        preview_browser_story_choice(raw, docs, stage=stage["id"],
                                     alternative=stage["alternatives"][0], authorized=False)
    forged = _receipt(docs, [])
    forged["source_digest"] = "f" * 64
    with pytest.raises(StudioQuestError):
        preview_browser_story_choice(json.dumps(forged).encode(), docs,
                                     stage=stage["id"],
                                     alternative=stage["alternatives"][0], authorized=True)
