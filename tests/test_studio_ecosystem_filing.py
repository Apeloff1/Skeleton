import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_work import build_work_graph
from skeleton.ai.game_builder.studio_ecosystem_journal import WorkJournal
from skeleton.ai.game_builder.studio_ecosystem_spool import ArtifactSpool
from skeleton.ai.game_builder.studio_ecosystem_filing import submit_local_artifact,review_local_artifact
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

def test_real_artifact_required_for_review_without_release_proof(tmp_path):
    root=tmp_path/"work"
    root.mkdir(mode=0o700)
    graph=build_work_graph(read_blueprint("studio_arena_fighting_glacial_fjord"))
    journal=WorkJournal(root,graph,authorized=True)
    spool=ArtifactSpool(root,authorized=True)
    journal.claim("source-canon",worker="worker",token="token",authorized=True)
    with pytest.raises(StudioQuestError):
        submit_local_artifact(journal,spool,task_id="source-canon",worker="worker",
                              token="token",sha256="a"*64,authorized=True)
    receipt=spool.ingest([b"untrusted design artifact"],authorized=True)
    submission=submit_local_artifact(journal,spool,task_id="source-canon",worker="worker",
                                      token="token",sha256=receipt["sha256"],authorized=True)
    assert submission["local_content_integrity_verified"]
    assert not submission["external_provenance_verified"]
    with pytest.raises(StudioQuestError):
        review_local_artifact(journal,spool,task_id="source-canon",reviewer="worker",
                              accepted=True,authorized=True)
    response=review_local_artifact(journal,spool,task_id="source-canon",reviewer="reviewer",
                                    accepted=True,authorized=True)
    assert response["review_accepted_as_claim"]
    assert response["release_certified"] is False
