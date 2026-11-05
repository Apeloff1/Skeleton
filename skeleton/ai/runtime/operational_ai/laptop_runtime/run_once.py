"""One native inference turn backed by committed SQLite receipts."""
from __future__ import annotations
import secrets
from .dispatcher import LaptopDispatcher
from .contracts import identifier,utf8

def generate_once(worker,question,*,session=None,request_id=None,seed=0,temperature=0.8):
    dispatcher=LaptopDispatcher(worker)
    if session is None:
        session=dispatcher.dispatch("create",{})["session_id"]
    if request_id is None:
        request_id="r_"+secrets.token_hex(16)
    output=dispatcher.dispatch("turn",{
        "session_id":identifier(session),"request_id":identifier(request_id),
        "prompt":utf8(question,maximum=dispatcher.limits.input_bytes),
        "seed":seed,"temperature":temperature})
    return {"session_id":session,"request_id":request_id,
            "receipt":output["receipt"],"model_source":"actual-offline-GGUF"}
