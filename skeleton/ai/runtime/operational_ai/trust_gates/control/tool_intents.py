"""Prepare/resolve/abort lifecycle for explicitly authorized read-only tool intents."""
from __future__ import annotations
from threading import RLock
from ..contracts import fail
from ..engine import validate

class ToolIntents:
    def __init__(self,maximum=1000):
        if type(maximum) is not int or not 1<=maximum<=100000:
            fail("invalid intent maximum")
        self._lock=RLock();self._maximum=maximum
        self._intents={}

    def prepare(self,*,id,grant,call):
        if type(id) is not str or not id or len(id)>96:
            fail("invalid intent identity")
        if type(grant) is not dict or type(call) is not dict:
            fail("grant and tool call required")
        validate("grant",grant)
        validate("tool",call)
        if grant["tool_id"]!=call["tool_id"] or grant["nonce"]!=call["grant_id"]:
            fail("tool intent not bound to exact delegated grant")
        with self._lock:
            if id in self._intents or len(self._intents)>=self._maximum:
                fail("duplicate or full tool intent catalog")
            self._intents[id]={"state":"prepared","grant":grant["nonce"],
                               "tool":grant["tool_id"],"result":None}
            return {"intent_id":id,"state":"prepared"}

    def resolve(self,id,*,approved=False,result_digest=None):
        if approved is not True: fail("operator resolution required")
        import re
        if type(result_digest) is not str or re.fullmatch("[0-9a-f]{64}",result_digest) is None:
            fail("resolved tool requires result digest")
        with self._lock:
            old=self._intents.get(id)
            if old is None or old["state"]!="prepared":
                fail("tool intent not in prepared state")
            old["state"]="resolved";old["result"]=result_digest
            return {"intent_id":id,"state":"resolved","result_sha256":result_digest}

    def abort(self,id):
        with self._lock:
            old=self._intents.get(id)
            if old is None or old["state"]!="prepared":
                fail("only prepared tool intent may be aborted")
            old["state"]="aborted"
            return {"intent_id":id,"state":"aborted"}
