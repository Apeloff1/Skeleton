"""Observed local host resource floor; unknown telemetry fails closed."""
from __future__ import annotations
from ..contracts import fail

def observe(*,state_dir,minimum_ram,minimum_disk):
    from skeleton.ai.runtime.operational_ai.laptop_runtime.device_observer import inspect_device
    from skeleton.ai.runtime.operational_ai.laptop_runtime.device_admission import admit
    data=inspect_device(state_dir)
    result=admit(data,minimum_available_memory=minimum_ram,
                 minimum_state_bytes=minimum_disk)
    if result["device_certified"] is not False:
        fail("resource observation may not claim device qualification")
    return {"observation":data,"floor":result,
            "real_model_generation_tested":False,
            "certified_hardware":False}
