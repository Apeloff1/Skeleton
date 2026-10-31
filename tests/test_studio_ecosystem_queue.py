import pytest
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_work import build_work_graph
from skeleton.ai.game_builder.studio_ecosystem_capacity import ProducerCapacity
from skeleton.ai.game_builder.studio_ecosystem_queue import plan_work_batch

def test_ready_producer_jobs_admit_only_available_resources():
    docs=read_blueprint("studio_arena_fighting_glacial_fjord")
    graph=build_work_graph(docs)
    done=["source-canon","quest-integration","scene-integration"]
    zero=plan_work_batch(graph,done,ProducerCapacity(100,100,1),
                         working_set_bytes=1_000,output_bytes=1_000,authorized=True)
    assert zero["admitted"]==[]
    assert zero["deferred"]
    host=ProducerCapacity(100_000_000,100_000_000,16)
    ready=plan_work_batch(graph,done,host,working_set_bytes=1_000_000,
                          output_bytes=1_000_000,authorized=True)
    assert ready["requested_ready"]>=5
    assert len(ready["admitted"])==ready["requested_ready"]
    assert ready["work_executed"] is False
    with pytest.raises(PermissionError):
        plan_work_batch(graph,done,host,working_set_bytes=1,
                        output_bytes=1,authorized=False)
