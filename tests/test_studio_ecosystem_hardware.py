from skeleton.ai.game_builder.studio_ecosystem_hardware import MemoryTelemetry,memory_admission
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
import pytest

def test_independent_gpu_unknown_does_not_fake_extra_ram():
    sample=MemoryTelemetry(1_000_000,2_000_000,None,None,
                           100_000_000,8)
    assert memory_admission(sample,working_bytes=100_000)["admitted_slots"]==8
    assert memory_admission(sample,working_bytes=100_000,gpu_bytes=1)["admitted_slots"]==0
    assert memory_admission(sample,working_bytes=100_000,spill_bytes=500_000)["admitted_slots"]==8

def test_explicit_unified_gpu_memory_is_charged_against_same_host_ram():
    sample=MemoryTelemetry(1_000_000,2_000_000,800_000,1_000_000,
                           100_000_000,8,gpu_available=700_000,
                           gpu_memory_is_shared=True)
    slots=memory_admission(sample,working_bytes=300_000,gpu_bytes=200_000)
    assert slots["admitted_slots"]==1
    assert slots["shared_gpu_ram_double_counted"] is False
    with pytest.raises(StudioQuestError):
        memory_admission(sample,working_bytes=True)
