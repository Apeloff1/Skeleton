from dataclasses import replace
import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_work import build_work_graph
from skeleton.ai.game_builder.studio_ecosystem_leases import open_leases,assign_lease
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError

def test_cas_lease_binds_worker_to_first_ready_stage():
    graph=build_work_graph(read_blueprint("studio_arena_fighting_glacial_fjord"))
    initial=open_leases(graph,authorized=True)
    assigned=assign_lease(initial,graph,task_id="source-canon",worker_id="worker-1",
                          expected_revision=0,authorized=True)
    assert assigned.revision==1 and assigned.assigned==(("source-canon","worker-1"),)
    with pytest.raises(StudioQuestError):
        assign_lease(assigned,graph,task_id="source-canon",worker_id="worker-2",
                     expected_revision=0,authorized=True)
    with pytest.raises(StudioQuestError):
        assign_lease(replace(initial,evidence_digest="0"*64),graph,
                     task_id="source-canon",worker_id="x",expected_revision=0,
                     authorized=True)
    with pytest.raises(PermissionError):
        open_leases(graph,authorized=False)
