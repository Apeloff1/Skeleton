"""retrieval_insertion: privacy — bounded operational AI contract.

The source digest, caller/model identity, resource limit and external
authority are never inferred from untrusted language-model output.
Actual native inference is delegated to the canonical installed GGUF spine.
"""
from . import PROFILE
from skeleton.ai.runtime.operational_ai.offline_cognition.core.metrics import Metrics
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import integer,refuse
def record(sink,outcome,*,elapsed_ms):
    if type(sink) is not Metrics:refuse("redacting telemetry sink required")
    integer(elapsed_ms,maximum=PROFILE.latency_ms)
    return sink.observe(PROFILE.name,outcome,elapsed_ms)
def snapshot(sink):
    if type(sink) is not Metrics:refuse("private source metrics required")
    return {**sink.snapshot(),"domain":PROFILE.name,
            "prompt_bytes_stored":0,"secret_bytes_stored":0}
