"""Postcommit UTF8 frame delivery with finite credit and ordered acknowledgments.

No claim to live native GGUF token streaming. It only transmits bytes that
the canonical durable SQLite execution spine already committed.
"""
from __future__ import annotations
from collections import deque
from threading import RLock
from ..contracts import fail

class PostcommitDelivery:
    def __init__(self,receipt,*,credit=8,frame_bytes=4096,max_frames=256):
        from skeleton.ai.runtime.operational_ai.laptop_runtime.postcommit_stream import chunks
        if type(credit) is not int or not 1<=credit<=64:
            fail("unbounded delivery credit")
        self._receipt=chunks(receipt,chunk_bytes=frame_bytes,max_chunks=max_frames)
        self._frames=tuple(self._receipt["frames"])
        self._lock=RLock()
        self._credit=credit
        self._next=0
        self._ack=-1
        self._inflight=deque()
        self._closed=False

    def next(self):
        with self._lock:
            if self._closed:fail("postcommit delivery already closed")
            if self._next>=len(self._frames):return None
            if len(self._inflight)>=self._credit:
                fail("delivery receiver has no remaining credits")
            frame=dict(self._frames[self._next])
            self._inflight.append(frame["index"])
            self._next+=1
            return frame

    def acknowledge(self,index):
        if type(index) is not int:fail("invalid frame ACK")
        with self._lock:
            if self._closed:fail("ACK after delivery close")
            if index<=self._ack or index>=self._next:
                fail("replayed or future ACK")
            if not self._inflight or index<self._inflight[0]:
                fail("ACK outside outstanding window")
            while self._inflight and self._inflight[0]<=index:
                self._inflight.popleft()
            self._ack=index
            return {"acknowledged_through":index,"pending":len(self._inflight)}

    def complete(self):
        with self._lock:
            if self._closed:fail("already completed delivery")
            if self._next!=len(self._frames) or self._inflight:
                fail("cannot complete with untransmitted/unacknowledged frames")
            self._closed=True
            return {"status":"postcommit-delivered",
                "frame_count":len(self._frames),
                "output_sha256":self._receipt["output_sha256"],
                "live_native_stream":False}
