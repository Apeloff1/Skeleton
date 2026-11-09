"""Stateful live speech session contracts for VOL-157."""
from __future__ import annotations
from dataclasses import dataclass,replace
from enum import Enum
import re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
class SpeechError(ValueError):pass
class SessionState(str,Enum): CONNECTED="connected";DISCONNECTED="disconnected";CANCELLED="cancelled";CLOSED="closed"
class SegmentState(str,Enum): PROVISIONAL="provisional";FINAL="final"
@dataclass(frozen=True,slots=True)
class SpeechSession:
 session_id:str;generation:int;state:SessionState;max_buffered_frames:int
 def __post_init__(self):
  if not _ID.fullmatch(self.session_id) or self.generation<1 or self.max_buffered_frames<1:raise SpeechError("invalid session")
@dataclass(frozen=True,slots=True)
class TranscriptSegment:
 session_id:str;generation:int;sequence:int;text:str;state:SegmentState
 def __post_init__(self):
  if self.sequence<0 or not self.text:raise SpeechError("invalid transcript segment")
@dataclass(frozen=True,slots=True)
class SpeechFrame:
 session_id:str;generation:int;sequence:int;timestamp_ms:int
class SpeechRuntime:
 def __init__(self,session):self.session=session;self._buffered=0;self._final=set()
 def accept_frame(self,frame):
  if self.session.state is not SessionState.CONNECTED or frame.session_id!=self.session.session_id or frame.generation!=self.session.generation:raise SpeechError("stale or inactive speech frame")
  if self._buffered>=self.session.max_buffered_frames:raise SpeechError("speech backpressure")
  self._buffered+=1
 def consume_frame(self):
  if self._buffered:self._buffered-=1
 def commit(self,segment):
  if segment.session_id!=self.session.session_id or segment.generation!=self.session.generation:raise SpeechError("stale transcript")
  if segment.state is SegmentState.PROVISIONAL:return False
  if segment.sequence in self._final:raise SpeechError("duplicate final segment")
  self._final.add(segment.sequence);return True
 def reconnect(self):
  if self.session.state is SessionState.CANCELLED or self.session.state is SessionState.CLOSED:raise SpeechError("terminal session")
  self.session=replace(self.session,generation=self.session.generation+1,state=SessionState.CONNECTED);self._buffered=0;return self.session
 def barge_in(self):
  if self.session.state is not SessionState.CONNECTED:raise SpeechError("inactive session")
  self._buffered=0;return "tts_cancelled"
 def cancel(self):self.session=replace(self.session,state=SessionState.CANCELLED);self._buffered=0
