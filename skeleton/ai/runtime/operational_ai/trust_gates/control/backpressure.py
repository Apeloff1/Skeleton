"""Credit-based response dispatch that fails closed on unacknowledged chunks."""
from __future__ import annotations
from collections import deque
from threading import RLock
from ..contracts import fail

class BackpressureWindow:
    def __init__(self,*,window=8,max_bytes=262144,max_frames=256):
        if (type(window) is not int or type(max_bytes) is not int or
            type(max_frames) is not int or not 1<=window<=64 or
            not 1<=max_bytes<=262144 or not 1<=max_frames<=4096):
            fail("invalid streaming backpressure policy")
        self._lock=RLock()
        self._window=window;self._max_bytes=max_bytes;self._max_frames=max_frames
        self._outstanding=deque()
        self._sent=0;self._acked=-1;self._bytes=0
        self._cancelled=False

    def publish(self,text):
        if type(text) is not str: fail("text frame required")
        try: size=len(text.encode("utf-8","strict"))
        except UnicodeError: fail("invalid streaming Unicode")
        with self._lock:
            if self._cancelled: fail("cancelled stream")
            if (len(self._outstanding)>=self._window or
                self._sent>=self._max_frames or self._bytes+size>self._max_bytes):
                fail("backpressure window saturated")
            frame={"index":self._sent,"text":text}
            self._outstanding.append(frame)
            self._sent+=1;self._bytes+=size
            return dict(frame)

    def acknowledge(self,index):
        if type(index) is not int: fail("ack index must be integer")
        with self._lock:
            if self._cancelled: fail("stream cancelled")
            if index<=self._acked: fail("duplicate or stale acknowledgement")
            if index>=self._sent: fail("acknowledged future frame")
            if not self._outstanding or index<self._outstanding[0]["index"]:
                fail("acknowledgement outside outstanding window")
            while self._outstanding and self._outstanding[0]["index"]<=index:
                self._outstanding.popleft()
            self._acked=index
            return self._acked

    def complete(self):
        with self._lock:
            if self._cancelled: fail("cancelled stream")
            if self._outstanding: fail("cannot finish before receiver acknowledgment")
            return {"frames":self._sent,"bytes":self._bytes,"acked_through":self._acked}

    def cancel(self):
        with self._lock:
            self._cancelled=True
            removed=len(self._outstanding)
            self._outstanding.clear()
            return {"cancelled":True,"dropped_unacknowledged_frames":removed}
