"""Temporal metadata sidecar for canonical retrieval fragments."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class TemporalFragment:
 fragment_id:str;source_url:str;observed_at:float;event_years:tuple[int,...];content_hash:str
class TemporalRetrievalCatalog:
 def __init__(self):self._rows={}
 def put(self,row):
  prior=self._rows.get(row.fragment_id)
  if prior is not None and prior!=row:raise ValueError("temporal fragment metadata changed for existing id")
  self._rows[row.fragment_id]=row
 def filter(self,fragment_ids,*,event_from=None,event_to=None,as_of=None):
  out=[]
  for fid in fragment_ids:
   row=self._rows.get(fid)
   if row is None:continue
   if as_of is not None and row.observed_at>as_of:continue
   if event_from is not None or event_to is not None:
    if not any((event_from is None or y>=event_from) and (event_to is None or y<=event_to) for y in row.event_years):continue
   out.append(fid)
  return tuple(out)
