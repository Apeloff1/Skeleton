"""Bounded audio envelope and timestamp provenance for VOL-156."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import math,re
_SHA=re.compile(r"^[0-9a-f]{64}$");_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
class AudioError(ValueError): pass
class AudioKind(str,Enum): SPEECH="speech"; MUSIC="music"; EVENT="event"
@dataclass(frozen=True,slots=True)
class AudioAsset:
 asset_id:str;source_digest:str;sample_rate:int;channels:int;duration_ms:int;encoded_bytes:int
 def __post_init__(self):
  if not _ID.fullmatch(self.asset_id) or not _SHA.fullmatch(self.source_digest) or min(self.sample_rate,self.channels,self.duration_ms,self.encoded_bytes)<1: raise AudioError("invalid audio asset")
@dataclass(frozen=True,slots=True)
class AudioLimits:
 max_duration_ms:int;max_channels:int;max_sample_rate:int;max_encoded_bytes:int
 def admit(self,a):
  if a.duration_ms>self.max_duration_ms or a.channels>self.max_channels or a.sample_rate>self.max_sample_rate or a.encoded_bytes>self.max_encoded_bytes: raise AudioError("audio exceeds decode limits")
  return True
@dataclass(frozen=True,slots=True)
class AudioSegment:
 asset_id:str;start_ms:int;end_ms:int
 def validate(self,a):
  if self.asset_id!=a.asset_id or self.start_ms<0 or self.end_ms<=self.start_ms or self.end_ms>a.duration_ms: raise AudioError("segment outside source timeline")
  return True
@dataclass(frozen=True,slots=True)
class AudioResult:
 segment:AudioSegment;kind:AudioKind;confidence:float;model_digest:str
 def __post_init__(self):
  if not math.isfinite(self.confidence) or not 0<=self.confidence<=1 or not _SHA.fullmatch(self.model_digest): raise AudioError("invalid audio result")