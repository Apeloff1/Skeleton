from dataclasses import dataclass
@dataclass(frozen=True)
class IndexWatermark:
 source_version:str; sequence:int
 def __post_init__(self):
  if not self.source_version or isinstance(self.sequence,bool) or not isinstance(self.sequence,int) or self.sequence<0:raise ValueError("valid source watermark required")
@dataclass(frozen=True)
class SearchIndex: name:str; version:str; watermark:IndexWatermark; derived:bool=True
@dataclass(frozen=True)
class IndexLifecycle:
 index:SearchIndex; retired:bool=False
 def __post_init__(self):
  if not self.index.derived:raise ValueError("search index cannot be authoritative")
 def refresh(self,w):
  if self.retired:raise PermissionError("retired index cannot refresh")
  if w.source_version!=self.index.watermark.source_version:raise ValueError("source version change requires rebuild")
  if w.sequence<self.index.watermark.sequence:raise ValueError("watermark regression")
  return IndexLifecycle(SearchIndex(self.index.name,self.index.version,w),self.retired)
