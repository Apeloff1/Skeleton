"""Coordinate-bound OCR/native-text fusion for VOL-155."""
from __future__ import annotations
from dataclasses import dataclass
import math,re
_SHA=re.compile(r"^[0-9a-f]{64}$");_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
class DocumentVisionError(ValueError): pass
@dataclass(frozen=True,slots=True)
class DocumentPage:
 document_id:str;page:int;render_digest:str;width:int;height:int
 def __post_init__(self):
  if not _ID.fullmatch(self.document_id) or self.page<1 or self.width<1 or self.height<1 or not _SHA.fullmatch(self.render_digest): raise DocumentVisionError("invalid page")
@dataclass(frozen=True,slots=True)
class LayoutRegion:
 page:int;x:int;y:int;width:int;height:int
 def validate(self,p):
  if self.page!=p.page or min(self.x,self.y)<0 or min(self.width,self.height)<1 or self.x+self.width>p.width or self.y+self.height>p.height: raise DocumentVisionError("region outside page")
  return True
@dataclass(frozen=True,slots=True)
class OCRSpan:
 region:LayoutRegion;text:str;confidence:float;model_digest:str
 def __post_init__(self):
  if not self.text or not math.isfinite(self.confidence) or not 0<=self.confidence<=1 or not _SHA.fullmatch(self.model_digest): raise DocumentVisionError("invalid OCR span")
@dataclass(frozen=True,slots=True)
class TextEvidence:
 region:LayoutRegion;text:str;source:str
@dataclass(frozen=True,slots=True)
class FusionResult:
 status:str;ocr_text:str;native_text:str|None
def fuse(page,ocr,native=None):
 ocr.region.validate(page)
 if native:
  native.region.validate(page)
  if native.region!=ocr.region: raise DocumentVisionError("evidence region mismatch")
  if native.text.strip()!=ocr.text.strip(): return FusionResult("conflict",ocr.text,native.text)
 return FusionResult("agree" if native else "ocr_only",ocr.text,native.text if native else None)