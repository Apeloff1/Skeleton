"""Deterministic year-aware evidence signals for governed learning and promotion."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json

class TemporalSignalError(ValueError): pass

def _digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

def _hex(value,name):
    if not isinstance(value,str) or len(value)!=64 or any(c not in "0123456789abcdef" for c in value):
        raise TemporalSignalError(f"invalid {name}")

def _year(value,name):
    if not isinstance(value,int) or isinstance(value,bool) or not 1900<=value<=2200:
        raise TemporalSignalError(f"invalid {name}")

@dataclass(frozen=True)
class YearSignal:
    signal_id:str
    subject:str
    event_year:int
    observed_year:int
    source_digest:str
    evidence_digest:str
    confidence_ppm:int
    polarity:int
    valid_through_year:int
    provenance_class:str
    def __post_init__(self):
        if not self.signal_id or not self.subject: raise TemporalSignalError("signal identity required")
        _year(self.event_year,"event_year"); _year(self.observed_year,"observed_year"); _year(self.valid_through_year,"valid_through_year")
        if self.observed_year<self.event_year: raise TemporalSignalError("observation predates event")
        if self.valid_through_year<self.event_year: raise TemporalSignalError("validity predates event")
        _hex(self.source_digest,"source_digest"); _hex(self.evidence_digest,"evidence_digest")
        if not isinstance(self.confidence_ppm,int) or isinstance(self.confidence_ppm,bool) or not 0<=self.confidence_ppm<=1_000_000: raise TemporalSignalError("invalid confidence")
        if self.polarity not in {-1,0,1}: raise TemporalSignalError("invalid polarity")
        if self.provenance_class not in {"primary","verified-secondary","derived"}: raise TemporalSignalError("invalid provenance class")
    @property
    def digest(self): return _digest(self.__dict__)

@dataclass(frozen=True)
class SignalAssessment:
    policy_year:int
    subject:str
    signal_digests:tuple[str,...]
    support_ppm:int
    oppose_ppm:int
    uncertainty_ppm:int
    stale_count:int
    contradiction:bool
    def __post_init__(self):
        _year(self.policy_year,"policy_year")
        for d in self.signal_digests: _hex(d,"signal_digest")
        if tuple(sorted(self.signal_digests))!=self.signal_digests or len(set(self.signal_digests))!=len(self.signal_digests): raise TemporalSignalError("signal digests must be unique and canonical")
        for n in ("support_ppm","oppose_ppm","uncertainty_ppm"):
            v=getattr(self,n)
            if not isinstance(v,int) or not 0<=v<=1_000_000: raise TemporalSignalError(f"invalid {n}")
    @property
    def digest(self): return _digest(self.__dict__)

def _effective_confidence(signal,policy_year,decay_ppm):
    if policy_year>signal.valid_through_year: return 0
    age=max(0,policy_year-signal.event_year)
    value=signal.confidence_ppm
    for _ in range(age): value=(value*decay_ppm)//1_000_000
    return value

def assess_year_signals(signals,*,policy_year,subject,annual_decay_ppm=900_000):
    _year(policy_year,"policy_year")
    if not isinstance(annual_decay_ppm,int) or not 0<=annual_decay_ppm<=1_000_000: raise TemporalSignalError("invalid annual decay")
    signals=tuple(signals)
    if not signals: raise TemporalSignalError("at least one signal required")
    if len({s.signal_id for s in signals})!=len(signals): raise TemporalSignalError("duplicate signal id")
    if any(s.subject!=subject for s in signals): raise TemporalSignalError("cross-subject signal contamination")
    if any(s.observed_year>policy_year for s in signals): raise TemporalSignalError("future-observed signal")
    support=oppose=stale=0
    for s in signals:
        effective=_effective_confidence(s,policy_year,annual_decay_ppm)
        if effective==0 and policy_year>s.valid_through_year: stale+=1
        if s.polarity>0: support+=effective
        elif s.polarity<0: oppose+=effective
    support=min(1_000_000,support); oppose=min(1_000_000,oppose)
    uncertainty=max(0,1_000_000-max(support,oppose))
    return SignalAssessment(policy_year,subject,tuple(sorted(s.digest for s in signals)),support,oppose,uncertainty,stale,support>0 and oppose>0)

def require_signal_authority(assessment,*,min_support_ppm=700_000,max_oppose_ppm=100_000,allow_contradiction=False):
    if assessment.support_ppm<min_support_ppm: raise TemporalSignalError("insufficient temporal support")
    if assessment.oppose_ppm>max_oppose_ppm: raise TemporalSignalError("temporal opposition exceeds policy")
    if assessment.contradiction and not allow_contradiction: raise TemporalSignalError("contradictory temporal evidence")
    return assessment.digest

__all__=["TemporalSignalError","YearSignal","SignalAssessment","assess_year_signals","require_signal_authority"]
