"""Bounded in-process response assembler, not a stand-in for native inference."""
from __future__ import annotations
from ..contracts import fail
from ..engine import validate

class StreamAssembler:
    def __init__(self, request_id, *, max_bytes=262144, token_ceiling=2048):
        if type(max_bytes) is not int or not 1<=max_bytes<=262144:
            fail("invalid stream byte ceiling")
        if type(token_ceiling) is not int or not 1<=token_ceiling<=8192:
            fail("invalid token ceiling")
        self.request_id=request_id
        self.max_bytes=max_bytes
        self.token_ceiling=token_ceiling
        self._chunks=[]
        self._bytes=0
        self._closed=False

    def append(self, text):
        if self._closed: fail("stream already finalized")
        if type(text) is not str: fail("stream chunk must be text")
        try: count=len(text.encode("utf-8","strict"))
        except UnicodeError: fail("malformed UTF8 output")
        if count>4096 or self._bytes+count>self.max_bytes or len(self._chunks)>=256:
            fail("stream budget exhausted")
        self._chunks.append({"index":len(self._chunks),"text":text})
        self._bytes+=count

    def finish(self, *, terminal="stop", generated_tokens=0):
        if self._closed: fail("stream double-finish")
        if not self._chunks: fail("stream must contain observed chunks")
        payload={"request_id":self.request_id,"chunks":self._chunks,
                 "max_bytes":self.max_bytes,"terminal":terminal,
                 "generated_tokens":generated_tokens,"token_ceiling":self.token_ceiling}
        receipt=validate("stream",payload)
        self._closed=True
        return {"receipt":receipt,"text":"".join(x["text"] for x in self._chunks)}
