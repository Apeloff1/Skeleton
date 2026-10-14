"""Resource-bounded temporal video provenance for VOL-158."""
from __future__ import annotations
from dataclasses import dataclass
import re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$");_SHA=re.compile(r"^[0-9a-f]{64}$")
class VideoError(ValueError):pass
@dataclass(frozen=True,slots=True)
class VideoAsset:
 asset_id:str;source_digest:str;width:int;height:int;duration_ms:int;frame_count:int;encoded_bytes:int
 def __post_init__(self):
  if not _ID.fullmatch(self.asset_id) or not _SHA.fullmatch(self.source_digest) or min(self.width,self.height,self.duration_ms,self.frame_count,self.encoded_bytes)<1:raise VideoError("invalid video asset")
@dataclass(frozen=True,slots=True)
class VideoLimits:
 max_pixels:int;max_duration_ms:int;max_frames:int;max_encoded_bytes:int
 def admit(self,a):
  if a.width*a.height>self.max_pixels or a.duration_ms>self.max_duration_ms or a.frame_count>self.max_frames or a.encoded_bytes>self.max_encoded_bytes:raise VideoError("video exceeds decode limits")
  return True
@dataclass(frozen=True,slots=True)
class VideoSegment:
 asset_id:str;start_ms:int;end_ms:int
 def validate(self,a):
  if self.asset_id!=a.asset_id or self.start_ms<0 or self.end_ms<=self.start_ms or self.end_ms>a.duration_ms:raise VideoError("segment outside source timeline")
  return True
@dataclass(frozen=True,slots=True)
class FrameSample:
 asset_id:str;source_timestamp_ms:int;sample_index:int;frame_digest:str
 def validate(self,a,segment):
  segment.validate(a)
  if self.asset_id!=a.asset_id or not segment.start_ms<=self.source_timestamp_ms<segment.end_ms or self.sample_index<0 or not _SHA.fullmatch(self.frame_digest):raise VideoError("invalid frame provenance")
  return True
def sample_timestamps(segment,interval_ms,max_samples):
 if interval_ms<1 or max_samples<1:raise VideoError("invalid sampling policy")
 points=tuple(range(segment.start_ms,segment.end_ms,interval_ms))
 if len(points)>max_samples:raise VideoError("sampling budget exceeded")
 return points
