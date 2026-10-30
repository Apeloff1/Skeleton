import pytest
from skeleton.ai.game_builder.studio_ecosystem_capacity import ProducerCapacity, plan_producer_admission
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
def test_capacity_expands_with_measured_resources_without_file_count_cap():
    small=ProducerCapacity(1_000_000,10_000_000,2)
    large=ProducerCapacity(100_000_000,100_000_000,16)
    a=plan_producer_admission(small,working_set_bytes=300_000,output_bytes=500_000)
    b=plan_producer_admission(large,working_set_bytes=300_000,output_bytes=500_000)
    assert a["admitted_worker_slots"]==2
    assert b["admitted_worker_slots"]==16
    assert not b["native_gpu_allocation_performed"]
def test_gpu_budget_unknown_fails_closed_but_known_capacity_is_not_double_counted():
    host=ProducerCapacity(1_000_000_000,1_000_000_000,16)
    result=plan_producer_admission(host,working_set_bytes=10_000,
                                   output_bytes=10_000,gpu_bytes=100_000)
    assert result["admitted_worker_slots"]==0
    with_gpu=ProducerCapacity(1_000_000_000,1_000_000_000,16,gpu_free_bytes=200_000)
    result=plan_producer_admission(with_gpu,working_set_bytes=10_000,
                                   output_bytes=10_000,gpu_bytes=100_000)
    assert result["admitted_worker_slots"]==1
    with pytest.raises(StudioQuestError):
        plan_producer_admission(with_gpu,working_set_bytes=True,output_bytes=1)
