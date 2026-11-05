"""Ordered digest-verified UTF8 postcommit frame protocol with finite credit."""
from __future__ import annotations
import hashlib
from collections import deque
from threading import RLock
from .contracts import integer,sha,text,hash_bytes,refuse
class Stream:
    def __init__(self,committed_text,output_sha256,*,frame_bytes=2048,credit=8):
        raw=text(committed_text,maximum=262144).encode("utf-8")
        if hash_bytes(raw)!=sha(output_sha256):refuse("output must be committed before streaming")
        integer(frame_bytes,minimum=1,maximum=65536)
        integer(credit,minimum=1,maximum=1024)
        pieces=[];offset=0;index=0
        while offset<len(raw):
            end=min(len(raw),offset+frame_bytes)
            # Do not split multibyte UTF8 codepoints across logical frames.
            while end<len(raw) and (raw[end]&0b11000000)==0b10000000:end-=1
            if end<=offset:refuse("frame capacity smaller than UTF8 codepoint")
            payload=raw[offset:end]
            pieces.append({"index":index,"text":payload.decode("utf-8"),
                "sha256":hash_bytes(payload),"start":offset,"end":end})
            offset=end;index+=1
        if len(pieces)>262144:refuse("unbounded stream frame count")
        self.frames=tuple(pieces);self.credit=credit
        self.lock=RLock();self.index=0;self.ack=-1;self.pending=deque()
        self.output_sha256=output_sha256
    def next(self):
        with self.lock:
            if self.index>=len(self.frames):return None
            if len(self.pending)>=self.credit:refuse("receiver streaming credit exhausted")
            part=dict(self.frames[self.index]);self.pending.append(part["index"])
            self.index+=1
            return part
    def acknowledge(self,index):
        integer(index,maximum=262144)
        with self.lock:
            if index<=self.ack or index>=self.index:
                refuse("replayed or future streaming ACK")
            if not self.pending or index<self.pending[0]:
                refuse("out-of-window frame ACK")
            while self.pending and self.pending[0]<=index:self.pending.popleft()
            self.ack=index
            return {"acknowledged_through":index,"pending":len(self.pending)}
    def complete(self):
        with self.lock:
            if self.pending or self.index!=len(self.frames):
                refuse("cannot complete an undelivered output")
            return {"sha256":self.output_sha256,"frames":len(self.frames),
                "postcommit_stream_only":True,"native_live_tokens":False}
