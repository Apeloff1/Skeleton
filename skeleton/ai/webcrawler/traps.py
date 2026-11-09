"""Deterministic crawl-trap detection before frontier admission."""
from __future__ import annotations
import re
from dataclasses import dataclass
from urllib.parse import parse_qsl,urlsplit
_CAL=re.compile(r"/(?:19|20)\d\d/(?:0?[1-9]|1[0-2])/(?:0?[1-9]|[12]\d|3[01])(?:/|$)")
_SESSION={"session","sessionid","sid","phpsessid","jsessionid","token"}
@dataclass(frozen=True)
class TrapDecision:
 allowed:bool;reason:str
class TrapGuard:
 def __init__(self,max_query_pairs=12,max_path_segments=20,max_repeated_segment=4):
  self.max_query_pairs=max_query_pairs;self.max_path_segments=max_path_segments;self.max_repeated_segment=max_repeated_segment
 def inspect(self,url):
  p=urlsplit(url);segments=[x for x in p.path.split("/") if x];pairs=parse_qsl(p.query,keep_blank_values=True)
  if len(pairs)>self.max_query_pairs:return TrapDecision(False,"query_explosion")
  if len(segments)>self.max_path_segments:return TrapDecision(False,"path_depth")
  if any(k.lower() in _SESSION for k,_ in pairs):return TrapDecision(False,"session_identifier")
  if segments and max(segments.count(x) for x in set(segments))>self.max_repeated_segment:return TrapDecision(False,"repeated_path")
  if _CAL.search(p.path) and any(k.lower() in {"next","prev","date","month","day"} for k,_ in pairs):
   return TrapDecision(False,"calendar_trap")
  return TrapDecision(True,"allowed")
