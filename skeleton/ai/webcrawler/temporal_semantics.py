"""Multi-time semantics for temporal research evidence."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime,timezone
import re
_DATE=re.compile(r"(?<!\d)((?:19|20)\d{2})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])(?!\d)")
_YEAR=re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
@dataclass(frozen=True)
class TemporalSemantics:
 observed_at:float;published_at:float|None;event_from_year:int|None;event_to_year:int|None
 confidence:float;basis:tuple[str,...]
def _epoch(y,m,d):
 try:return datetime(int(y),int(m),int(d),tzinfo=timezone.utc).timestamp()
 except ValueError:return None
def infer_temporal_semantics(text,*,observed_at,published_hint=None):
 dates=[_epoch(*m) for m in _DATE.findall(text[:4000])];dates=[x for x in dates if x is not None]
 years=sorted({int(x) for x in _YEAR.findall(text[:4000])})
 published=published_hint if published_hint is not None else (max((x for x in dates if x<=observed_at),default=None))
 basis=[]
 if published is not None:basis.append("explicit-or-hinted-publication-date")
 if years:basis.append("explicit-subject-year")
 confidence=min(1.0,.35+.30*bool(published is not None)+.20*bool(years)+.15*bool(len(years)>1))
 return TemporalSemantics(float(observed_at),published,years[0] if years else None,years[-1] if years else None,confidence,tuple(basis))
