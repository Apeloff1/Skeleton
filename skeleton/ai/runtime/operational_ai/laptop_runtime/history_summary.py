"""Derived, no-content session inventory with strict output bounds."""
from __future__ import annotations
import hashlib
from .contracts import canonical,identifier,refuse

def summary(worker,session_id,*,maximum=128):
    session_id=identifier(session_id)
    if type(maximum) is not int or not 1<=maximum<=128:
        refuse("invalid history summary ceiling")
    history=worker.spine.history(session_id)
    if not isinstance(history,(tuple,list)) or len(history)>maximum:
        refuse("unbounded history received")
    entries=[]
    for index,turn in enumerate(history):
        if type(turn) is not dict:
            refuse("noncanonical history turn")
        raw=canonical(turn,ceiling=262144)
        entries.append({"index":index,"sha256":hashlib.sha256(raw).hexdigest(),
                        "bytes":len(raw)})
    return {"session_id":session_id,"count":len(entries),"turns":entries,
            "contains_plaintext":False}
