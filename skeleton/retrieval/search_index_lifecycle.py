from dataclasses import dataclass
@dataclass(frozen=True)
class IndexWatermark: source_version:str; sequence:int
@dataclass(frozen=True)
class SearchIndex: name:str; version:str; watermark:IndexWatermark; derived:bool=True
@dataclass(frozen=True)
class IndexLifecycle:
 index:SearchIndex; retired:bool=False
 def __post_init__(self):
  if not self.index.derived:raise ValueError("search index cannot be authoritative")
 def refresh(self,w):
  if w.sequence<self.index.watermark.sequence:raise ValueError("watermark regression")
  return IndexLifecycle(SearchIndex(self.index.name,self.index.version,w),self.retired)
