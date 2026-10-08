"""Deterministic year- and decade-aware evidence signals for governed AI."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json

class TemporalSignalError(ValueError): pass
def _digest(v): return sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
def _hex(v,n):
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise TemporalSignalError(f"invalid {n}")
def _year(v,n):
    if not isinstance(v,int) or isinstance(v,bool) or not 1900<=v<=2200: raise TemporalSignalError(f"invalid {n}")
def decade_of(year): _year(year,"year"); return (year//10)*10

@dataclass(frozen=True)
class YearSignal:
    signal_id:str; subject:str; event_year:int; observed_year:int; source_digest:str; evidence_digest:str
    confidence_ppm:int; polarity:int; valid_through_year:int; provenance_class:str
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
class EraBoundary:
    boundary_id:str; subject:str; start_year:int; authority_digest:str; pre_boundary_retention_ppm:int=0
    def __post_init__(self):
        if not self.boundary_id or not self.subject: raise TemporalSignalError("era boundary identity required")
        _year(self.start_year,"start_year"); _hex(self.authority_digest,"authority_digest")
        if not isinstance(self.pre_boundary_retention_ppm,int) or not 0<=self.pre_boundary_retention_ppm<=1_000_000: raise TemporalSignalError("invalid era retention")
    @property
    def digest(self): return _digest(self.__dict__)

@dataclass(frozen=True)
class DecadePolicy:
    policy_id:str; subject:str; policy_decade:int; prior_decade_retention_ppm:int; max_decades_back:int; authority_digest:str
    def __post_init__(self):
        if not self.policy_id or not self.subject: raise TemporalSignalError("decade policy identity required")
        _year(self.policy_decade,"policy_decade")
        if self.policy_decade%10: raise TemporalSignalError("policy decade must start on decade boundary")
        if not isinstance(self.prior_decade_retention_ppm,int) or not 0<=self.prior_decade_retention_ppm<=1_000_000: raise TemporalSignalError("invalid decade retention")
        if not isinstance(self.max_decades_back,int) or isinstance(self.max_decades_back,bool) or not 0<=self.max_decades_back<=30: raise TemporalSignalError("invalid decade horizon")
        _hex(self.authority_digest,"authority_digest")
    @property
    def digest(self): return _digest(self.__dict__)

@dataclass(frozen=True)
class SignalAssessment:
    policy_year:int; subject:str; signal_digests:tuple[str,...]; support_ppm:int; oppose_ppm:int
    uncertainty_ppm:int; stale_count:int; contradiction:bool
    def __post_init__(self):
        _year(self.policy_year,"policy_year")
        for d in self.signal_digests: _hex(d,"signal_digest")
        if tuple(sorted(self.signal_digests))!=self.signal_digests or len(set(self.signal_digests))!=len(self.signal_digests): raise TemporalSignalError("signal digests must be unique and canonical")
    @property
    def digest(self): return _digest(self.__dict__)

@dataclass(frozen=True)
class DecadeAssessment:
    policy_decade:int; subject:str; policy_digest:str; signal_digests:tuple[str,...]
    support_ppm:int; oppose_ppm:int; excluded_count:int; oldest_included_decade:int; contradiction:bool
    @property
    def digest(self): return _digest(self.__dict__)

def _effective(s,policy_year,annual_decay_ppm):
    if policy_year>s.valid_through_year: return 0
    v=s.confidence_ppm
    for _ in range(max(0,policy_year-s.event_year)): v=(v*annual_decay_ppm)//1_000_000
    return v

def assess_year_signals(signals,*,policy_year,subject,annual_decay_ppm=900_000,era_boundaries=()):
    _year(policy_year,"policy_year"); signals=tuple(signals); boundaries=tuple(era_boundaries)
    if not signals: raise TemporalSignalError("at least one signal required")
    if len({s.signal_id for s in signals})!=len(signals): raise TemporalSignalError("duplicate signal id")
    if any(s.subject!=subject for s in signals): raise TemporalSignalError("cross-subject signal contamination")
    if any(s.observed_year>policy_year for s in signals): raise TemporalSignalError("future-observed signal")
    if any(b.subject!=subject for b in boundaries): raise TemporalSignalError("cross-subject era boundary")
    if any(b.start_year>policy_year for b in boundaries): raise TemporalSignalError("future era boundary")
    support=oppose=stale=0
    for s in signals:
        v=_effective(s,policy_year,annual_decay_ppm)
        for b in boundaries:
            if s.event_year<b.start_year: v=(v*b.pre_boundary_retention_ppm)//1_000_000
        if v==0 and policy_year>s.valid_through_year: stale+=1
        if s.polarity>0: support+=v
        elif s.polarity<0: oppose+=v
    support=min(1_000_000,support); oppose=min(1_000_000,oppose)
    return SignalAssessment(policy_year,subject,tuple(sorted(s.digest for s in signals)),support,oppose,max(0,1_000_000-max(support,oppose)),stale,support>0 and oppose>0)

def assess_decade_signals(signals,*,policy:DecadePolicy,policy_year:int):
    _year(policy_year,"policy_year")
    if decade_of(policy_year)!=policy.policy_decade: raise TemporalSignalError("policy year outside policy decade")
    signals=tuple(signals)
    if not signals: raise TemporalSignalError("at least one signal required")
    if len({s.signal_id for s in signals})!=len(signals): raise TemporalSignalError("duplicate signal id")
    if any(s.subject!=policy.subject for s in signals): raise TemporalSignalError("cross-subject decade contamination")
    if any(s.observed_year>policy_year for s in signals): raise TemporalSignalError("future-observed signal")
    support=oppose=excluded=0; included=[]
    for s in signals:
        distance=(policy.policy_decade-decade_of(s.event_year))//10
        if distance<0: raise TemporalSignalError("future-decade signal")
        if distance>policy.max_decades_back or policy_year>s.valid_through_year: excluded+=1; continue
        v=s.confidence_ppm
        for _ in range(distance): v=(v*policy.prior_decade_retention_ppm)//1_000_000
        included.append(decade_of(s.event_year))
        if s.polarity>0: support+=v
        elif s.polarity<0: oppose+=v
    support=min(1_000_000,support); oppose=min(1_000_000,oppose)
    oldest=min(included) if included else policy.policy_decade
    return DecadeAssessment(policy.policy_decade,policy.subject,policy.digest,tuple(sorted(s.digest for s in signals)),support,oppose,excluded,oldest,support>0 and oppose>0)

@dataclass(frozen=True)
class TemporalConsensus:
    subject:str; policy_year:int; year_assessment_digest:str; decade_assessment_digest:str
    support_floor_ppm:int; opposition_ceiling_ppm:int; contradiction:bool
    @property
    def digest(self): return _digest(self.__dict__)

def reconcile_temporal_scales(year_assessment,decade_assessment):
    if year_assessment.subject!=decade_assessment.subject: raise TemporalSignalError("temporal scale subject mismatch")
    if decade_of(year_assessment.policy_year)!=decade_assessment.policy_decade: raise TemporalSignalError("temporal scale period mismatch")
    return TemporalConsensus(year_assessment.subject,year_assessment.policy_year,year_assessment.digest,decade_assessment.digest,min(year_assessment.support_ppm,decade_assessment.support_ppm),max(year_assessment.oppose_ppm,decade_assessment.oppose_ppm),year_assessment.contradiction or decade_assessment.contradiction)

def require_consensus_authority(consensus,*,min_support_ppm=700_000,max_oppose_ppm=100_000):
    if consensus.support_floor_ppm<min_support_ppm: raise TemporalSignalError("cross-scale temporal support insufficient")
    if consensus.opposition_ceiling_ppm>max_oppose_ppm: raise TemporalSignalError("cross-scale temporal opposition exceeds policy")
    if consensus.contradiction: raise TemporalSignalError("cross-scale temporal contradiction")
    return consensus.digest

def require_signal_authority(a,*,min_support_ppm=700_000,max_oppose_ppm=100_000,allow_contradiction=False):
    if a.support_ppm<min_support_ppm: raise TemporalSignalError("insufficient temporal support")
    if a.oppose_ppm>max_oppose_ppm: raise TemporalSignalError("temporal opposition exceeds policy")
    if a.contradiction and not allow_contradiction: raise TemporalSignalError("contradictory temporal evidence")
    return a.digest

__all__=["TemporalSignalError","YearSignal","EraBoundary","DecadePolicy","SignalAssessment","DecadeAssessment","decade_of","assess_year_signals","assess_decade_signals","TemporalConsensus","reconcile_temporal_scales","require_consensus_authority","require_signal_authority"]
