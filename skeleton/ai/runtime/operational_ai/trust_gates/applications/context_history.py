"""Transcript-order verifier and bounded next-user context preparation."""
from __future__ import annotations
from ..contracts import fail
from ..engine import validate

def prepare_history(session_id, messages, next_user, *, revision=0,
                    max_bytes=65536):
    if type(messages) not in (tuple,list) or type(next_user) is not str:
        fail("invalid transcript input")
    if type(max_bytes) is not int or not 1<=max_bytes<=262144:
        fail("invalid context ceiling")
    if len(messages)>126: fail("too many observed messages")
    normalized=[]
    for entry in messages:
        if type(entry) is not dict or set(entry)!={"role","content"}:
            fail("unknown transcript fields")
        if entry["role"] not in ("system","user","assistant"):
            fail("untrusted transcript role")
        normalized.append({"role":entry["role"],"content":entry["content"]})
    if normalized and normalized[0]["role"]=="system":
        turns=normalized[1:]
    else:
        turns=normalized
    for idx,entry in enumerate(turns):
        expected="user" if idx%2==0 else "assistant"
        if entry["role"]!=expected:
            fail("nonalternating committed conversation")
    if len(turns)%2:
        fail("unfinished assistant turn before next user input")
    normalized.append({"role":"user","content":next_user})
    receipt=validate("conversation",{
        "session_id":session_id,"messages":normalized,
        "max_bytes":max_bytes,"revision":revision,"final_role":"user"})
    return {"messages":normalized,"receipt":receipt}
