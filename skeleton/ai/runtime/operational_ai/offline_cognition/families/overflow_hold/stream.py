"""overflow_hold: stream — bounded operational AI contract.

The source digest, caller/model identity, resource limit and external
authority are never inferred from untrusted language-model output.
Actual native inference is delegated to the canonical installed GGUF spine.
"""
from . import PROFILE
from skeleton.ai.runtime.operational_ai.offline_cognition.core.stream import Stream
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import refuse
def postcommit(text,output_sha256,*,frame_bytes=2048,credit=8):
    return Stream(text,output_sha256,frame_bytes=frame_bytes,credit=credit)
def drain(channel):
    if type(channel) is not Stream:refuse("committed output channel required")
    sent=[]
    while True:
        frame=channel.next()
        if frame is None:break
        sent.append(frame)
        channel.acknowledge(frame["index"])
    return {"frames":tuple(sent),"receipt":channel.complete(),
            "native_live_streaming_proved":False}
