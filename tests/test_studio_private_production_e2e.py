"""End-to-end source-pinned producer acceptance; real bytes, no release inflation."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_work import build_work_graph
from skeleton.ai.game_builder.studio_ecosystem_journal import WorkJournal
from skeleton.ai.game_builder.studio_ecosystem_supervisor import StudioSupervisor
from skeleton.ai.game_builder.studio_ecosystem_spool import ArtifactSpool
from skeleton.ai.game_builder.studio_ecosystem_fence import (
    assert_source_fence, pin_source_sections,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, start_quest, step_quest,
)
from skeleton.ai.game_builder.studio_ecosystem_checkpoint_store import (
    persist_quest_checkpoint, resume_quest_checkpoint,
)
from skeleton.ai.game_builder.studio_ecosystem_preview_worker import (
    compile_and_spool_preview,
)
from skeleton.ai.game_builder.studio_ecosystem_spool_audit import audit_artifact_spool


def _root(tmp_path):
    root=tmp_path/"private"
    root.mkdir(mode=0o700)
    return root


def test_two_workers_compete_for_exactly_one_task(tmp_path):
    root=_root(tmp_path)
    project="studio_arena_fighting_glacial_fjord"
    a=StudioSupervisor(root,project,authorized=True)
    b=StudioSupervisor(root,project,authorized=True)
    def attempt(pair):
        supervisor, worker=pair
        try:
            supervisor.claim("source-canon",worker=worker,
                             token="capability-"+worker,authorized=True)
            return True
        except StudioQuestError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes=list(pool.map(attempt,[(a,"workerA"),(b,"workerB")]))
    assert sorted(outcomes)==[False,True]
    assert WorkJournal(root,build_work_graph(read_blueprint(project)),
                       authorized=True).verify_state()["local_lifecycle_replay_valid"]


def test_complete_local_authoring_delivery_does_not_certify_the_game(tmp_path):
    root=_root(tmp_path)
    project="studio_aerial_traversal_amber_highlands"
    owner=StudioSupervisor(root,project,authorized=True)
    owner.claim("source-canon",worker="author",token="first",authorized=True)
    supplied=owner.submit("source-canon",worker="author",token="first",
                          chunks=[b"original authored world evidence"],authorized=True)
    assert supplied["local_content_integrity_verified"]
    accepted=owner.review("source-canon",reviewer="reviewer",
                           accepted=True,authorized=True)
    assert not accepted["external_evidence_verified"]
    second=StudioSupervisor(root,project,authorized=True)
    second.claim("quest-integration",worker="integrator",token="second",authorized=True)
    preview=compile_and_spool_preview(second.journal,second.spool,authorized=True)
    assert second.spool.verify(preview["html_sha256"])==preview["html_bytes"]
    docs=read_blueprint(project)
    start=start_quest(docs,authorized=True)
    session=step_quest(start,docs,stage="arrival",alternative="inspect_markers",
                       authorized=True)
    checkpoint=persist_quest_checkpoint(second.journal,second.spool,session,
                                         authorized=True)
    recovered=StudioSupervisor(root,project,authorized=True)
    resumed=resume_quest_checkpoint(recovered.journal,recovered.spool,
                                    checkpoint=checkpoint,authorized=True)
    assert resumed==session
    assert recovered.resume(authorized=True)["leases_requiring_manual_recovery"]
    census=audit_artifact_spool(recovered.spool,authorized=True)
    assert census["local_content_consistent"]
    assert census["valid_artifacts"]>=3
    assert not preview["consumer_release_certified"]
    assert not checkpoint["release_certified"]
    assert not recovered.resume(authorized=True)["release_certified"]


def test_live_visual_canon_change_cannot_be_silently_reused(tmp_path):
    root=_root(tmp_path)
    docs=read_blueprint("studio_arena_fighting_glacial_fjord")
    journal=WorkJournal(root,build_work_graph(docs),authorized=True)
    pin_source_sections(journal,docs,authorized=True)
    altered=deepcopy(docs)
    altered["visual"]["art_direction"]["palette"][0]="#FFFFFF"
    with pytest.raises(StudioQuestError):
        assert_source_fence(journal,altered,authorized=True)
    with pytest.raises(StudioQuestError):
        pin_source_sections(journal,altered,authorized=True)
