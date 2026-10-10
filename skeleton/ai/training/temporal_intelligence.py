"""Higher-order temporal intelligence over year/era/decade evidence."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from .temporal_signals import YearSignal,DecadePolicy,TemporalSignalError,decade_of,assess_year_signals,assess_decade_signals,reconcile_temporal_scales,require_consensus_authority

def _digest(v): return sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
def _ppm(v,n):
 if not isinstance(v,int) or isinstance(v,bool) or not 0<=v<=1_000_000: raise TemporalSignalError(f"invalid {n}")
def _hex(v,n):
 if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise TemporalSignalError(f"invalid {n}")

@dataclass(frozen=True)
class DecadeProfile:
 decade:int; subject:str; signal_count:int; source_count:int; primary_count:int
 support_ppm:int; oppose_ppm:int; neutral_ppm:int; diversity_ppm:int; corroboration_ppm:int
 def __post_init__(self):
  if decade%10: raise TemporalSignalError("profile decade boundary required")
  for n in ("support_ppm","oppose_ppm","neutral_ppm","diversity_ppm","corroboration_ppm"): _ppm(getattr(self,n),n)
 @property
 def digest(self): return _digest(self.__dict__)

@dataclass(frozen=True)
class DecadeTransition:
 subject:str; from_decade:int; to_decade:int; support_delta_ppm:int; opposition_delta_ppm:int
 source_turnover_ppm:int; polarity_flip:bool; regime_shift_ppm:int
 def __post_init__(self):
  if self.from_decade%10 or self.to_decade%10 or self.to_decade-self.from_decade!=10: raise TemporalSignalError("transitions require adjacent decades")
  for n in ("source_turnover_ppm","regime_shift_ppm"): _ppm(getattr(self,n),n)
  for n in ("support_delta_ppm","opposition_delta_ppm"):
   if not isinstance(getattr(self,n),int) or not -1_000_000<=getattr(self,n)<=1_000_000: raise TemporalSignalError(f"invalid {n}")
 @property
 def digest(self): return _digest(self.__dict__)

@dataclass(frozen=True)
class TemporalTrend:
 subject:str; start_decade:int; end_decade:int; profile_digests:tuple[str,...]; transition_digests:tuple[str,...]
 momentum_ppm:int; volatility_ppm:int; regime_shift_count:int; direction:str
 @property
 def digest(self): return _digest(self.__dict__)

@dataclass(frozen=True)
class TemporalAuthorityReceipt:
 subject:str; policy_year:int; consensus_digest:str; trend_digest:str; source_diversity_ppm:int
 support_floor_ppm:int; volatility_ppm:int; regime_shift_count:int; authorized:bool
 def __post_init__(self):
  if not isinstance(self.subject,str) or not self.subject.strip(): raise TemporalSignalError("temporal authority subject required")
  if isinstance(self.policy_year,bool) or not isinstance(self.policy_year,int) or not 1000<=self.policy_year<=9999: raise TemporalSignalError("invalid temporal authority year")
  _hex(self.consensus_digest,"consensus"); _hex(self.trend_digest,"trend")
  for n in ("source_diversity_ppm","support_floor_ppm","volatility_ppm"): _ppm(getattr(self,n),n)
  if isinstance(self.regime_shift_count,bool) or not isinstance(self.regime_shift_count,int) or self.regime_shift_count<0: raise TemporalSignalError("invalid regime shift count")
  if not isinstance(self.authorized,bool): raise TemporalSignalError("invalid temporal authorization flag")
 @property
 def digest(self): return _digest(self.__dict__)

def build_decade_profiles(signals,*,subject):
 signals=tuple(signals)
 if not signals: raise TemporalSignalError("signals required")
 if any(s.subject!=subject for s in signals): raise TemporalSignalError("profile subject mismatch")
 groups={}
 for s in signals: groups.setdefault(decade_of(s.event_year),[]).append(s)
 out=[]
 for decade in sorted(groups):
  g=groups[decade]; sources={s.source_digest for s in g}; positives=sum(s.confidence_ppm for s in g if s.polarity>0); negatives=sum(s.confidence_ppm for s in g if s.polarity<0); neutrals=sum(s.confidence_ppm for s in g if s.polarity==0)
  total=max(1,positives+negatives+neutrals)
  diversity=min(1_000_000,(len(sources)*1_000_000)//len(g))
  evidence_groups={}
  for s in g: evidence_groups.setdefault(s.evidence_digest,set()).add(s.source_digest)
  corroborated=sum(1 for x in evidence_groups.values() if len(x)>=2)
  corroboration=(corroborated*1_000_000)//max(1,len(evidence_groups))
  out.append(DecadeProfile(decade,subject,len(g),len(sources),sum(s.provenance_class=="primary" for s in g),min(1_000_000,(positives*1_000_000)//total),min(1_000_000,(negatives*1_000_000)//total),min(1_000_000,(neutrals*1_000_000)//total),diversity,corroboration))
 return tuple(out)

def build_decade_transitions(profiles,signals):
 profiles=tuple(profiles); signals=tuple(signals); by_decade={}
 for s in signals: by_decade.setdefault(decade_of(s.event_year),set()).add(s.source_digest)
 out=[]
 for a,b in zip(profiles,profiles[1:]):
  if b.decade-a.decade!=10: continue
  sa=by_decade.get(a.decade,set()); sb=by_decade.get(b.decade,set()); union=sa|sb
  turnover=0 if not union else ((len(union)-len(sa&sb))*1_000_000)//len(union)
  sd=b.support_ppm-a.support_ppm; od=b.oppose_ppm-a.oppose_ppm
  flip=(a.support_ppm>a.oppose_ppm)!=(b.support_ppm>b.oppose_ppm)
  shift=min(1_000_000,(abs(sd)+abs(od)+turnover+(1_000_000 if flip else 0))//4)
  out.append(DecadeTransition(a.subject,a.decade,b.decade,sd,od,turnover,flip,shift))
 return tuple(out)

def analyze_temporal_trend(profiles,transitions,*,shift_threshold_ppm=400_000):
 profiles=tuple(profiles); transitions=tuple(transitions)
 if not profiles: raise TemporalSignalError("profiles required")
 _ppm(shift_threshold_ppm,"shift threshold")
 subject=profiles[0].subject
 if any(p.subject!=subject for p in profiles) or any(t.subject!=subject for t in transitions): raise TemporalSignalError("trend subject mismatch")
 net=[p.support_ppm-p.oppose_ppm for p in profiles]
 momentum=0 if len(net)<2 else max(-1_000_000,min(1_000_000,(net[-1]-net[0])//(len(net)-1)))
 mean=sum(net)//len(net); volatility=min(1_000_000,sum(abs(x-mean) for x in net)//len(net))
 shifts=sum(t.regime_shift_ppm>=shift_threshold_ppm for t in transitions)
 direction="rising" if momentum>50_000 else "falling" if momentum<-50_000 else "stable"
 return TemporalTrend(subject,profiles[0].decade,profiles[-1].decade,tuple(p.digest for p in profiles),tuple(t.digest for t in transitions),momentum,volatility,shifts,direction)

def authorize_temporal_evidence(signals,*,policy_year,subject,decade_policy,era_boundaries=(),min_diversity_ppm=500_000,max_volatility_ppm=500_000):
 signals=tuple(signals)
 year=assess_year_signals(signals,policy_year=policy_year,subject=subject,era_boundaries=era_boundaries)
 decade=assess_decade_signals(signals,policy=decade_policy,policy_year=policy_year)
 consensus=reconcile_temporal_scales(year,decade); require_consensus_authority(consensus)
 profiles=build_decade_profiles(signals,subject=subject); transitions=build_decade_transitions(profiles,signals); trend=analyze_temporal_trend(profiles,transitions)
 diversity=min(p.diversity_ppm for p in profiles)
 _ppm(min_diversity_ppm,"minimum diversity"); _ppm(max_volatility_ppm,"maximum volatility")
 if diversity<min_diversity_ppm: raise TemporalSignalError("insufficient temporal source diversity")
 if trend.volatility_ppm>max_volatility_ppm: raise TemporalSignalError("temporal volatility exceeds policy")
 return TemporalAuthorityReceipt(subject,policy_year,consensus.digest,trend.digest,diversity,consensus.support_floor_ppm,trend.volatility_ppm,trend.regime_shift_count,True)

__all__=["DecadeProfile","DecadeTransition","TemporalTrend","TemporalAuthorityReceipt","build_decade_profiles","build_decade_transitions","analyze_temporal_trend","authorize_temporal_evidence"]
