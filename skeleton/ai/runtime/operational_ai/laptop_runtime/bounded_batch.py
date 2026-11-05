"""Sequential live inference with no automatic re-generation on uncertain failure."""
from __future__ import annotations
from .contracts import refuse,utf8
from .live_session import LiveSession

def run(worker,prompts,*,limit=8,approved=False):
    if approved is not True:refuse("batch real inference requires operator approval")
    if type(prompts) not in (tuple,list) or not 1<=len(prompts)<=limit<=16:
        refuse("unbounded or empty native inference batch")
    for prompt in prompts:
        utf8(prompt,maximum=worker.spine.limits.input_bytes)
    session=LiveSession(worker)
    receipts=[]
    try:
        for prompt in prompts:
            # A failure stops the batch. Do not guess whether native effects
            # committed; never issue a replacement request automatically.
            receipts.append(session.turn(prompt))
        return {"schema":"laptop-live-batch.v1","session_id":session.session_id,
                "turns":receipts,"native_generation_count":len(receipts),
                "release_certified":False}
    except BaseException:
        raise
