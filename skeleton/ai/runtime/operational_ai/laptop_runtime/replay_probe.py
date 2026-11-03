"""Read-only exact-request durable replay proof without triggering generation."""
from __future__ import annotations
from .contracts import identifier,utf8,nonnegative,number,refuse
from .result_protocol import verify_turn_receipt
from .identity import ActiveModel

def inspect_replay(worker,session_id,request_id,prompt,*,seed=0,temperature=0.8):
    identity=ActiveModel.from_supervisor(worker)
    result=worker.spine.replay(identifier(session_id),identifier(request_id),
        utf8(prompt,maximum=worker.spine.limits.input_bytes),
        seed=nonnegative(seed,maximum=2**32-1),
        temperature=number(temperature,minimum=0.000000001,maximum=2))
    if result is None:
        return {"committed":False,"no_second_generation":True}
    verified=verify_turn_receipt(result,model_sha256=identity.model_sha256,
                                  tokenizer_sha256=identity.tokenizer_sha256)
    if verified["replayed"] is not True:
        refuse("durable replay was not marked replayed")
    return {"committed":True,"no_second_generation":True,
            "output_sha256":verified["output_sha256"]}
