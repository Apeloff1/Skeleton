"""Resource-bounded, provenance-preserving vision contracts for VOL-154."""
from __future__ import annotations
from dataclasses import dataclass
import math,re
_SHA=re.compile(r"^[0-9a-f]{64}$");_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
class VisionError(ValueError):pass
@dataclass(frozen=True,slots=True)
class ImageAsset:
 asset_id:str;source_digest:str;format:str;width:int;height:int;encoded_bytes:int
 def __post_init__(self):
  if not _ID.fullmatch(self.asset_id):raise VisionError("invalid asset id")
  if not _SHA.fullmatch(self.source_digest):raise VisionError("source digest required")
  if self.width<1 or self.height<1 or self.encoded_bytes<1:raise VisionError("invalid image dimensions")
@dataclass(frozen=True,slots=True)
class ImageLimits:
 max_width:int;max_height:int;max_pixels:int;max_encoded_bytes:int
 def admit(self,a):
  if a.width>self.max_width or a.height>self.max_height or a.width*a.height>self.max_pixels or a.encoded_bytes>self.max_encoded_bytes:raise VisionError("image exceeds decode limits")
  return True
@dataclass(frozen=True,slots=True)
class ImageRegion:
 asset_id:str;x:int;y:int;width:int;height:int;transform_digest:str
 def __post_init__(self):
  if min(self.x,self.y)<0 or min(self.width,self.height)<1:raise VisionError("invalid region")
  if not _SHA.fullmatch(self.transform_digest):raise VisionError("transform digest required")
 def validate(self,a):
  if self.asset_id!=a.asset_id or self.x+self.width>a.width or self.y+self.height>a.height:raise VisionError("region outside source image")
  return True
@dataclass(frozen=True,slots=True)
class VisionResult:
 region:ImageRegion;model_digest:str;confidence:float;result_digest:str
 def __post_init__(self):
  if not _SHA.fullmatch(self.model_digest) or not _SHA.fullmatch(self.result_digest):raise VisionError("result/model digest required")
  if not math.isfinite(self.confidence) or not 0<=self.confidence<=1:raise VisionError("invalid confidence")
