from dataclasses import dataclass
import math
@dataclass(frozen=True)
class SourceCluster: cluster_id:str; members:tuple[str,...]; owner:str; lineage_root:str
@dataclass(frozen=True)
class EvidenceIndependence: independent_clusters:int; total_sources:int
@dataclass(frozen=True)
class DiversityScore: score:float; quality_floor_met:bool
def diversity(clusters,quality_scores,min_quality):
 cs=tuple(clusters);qs=tuple(quality_scores)
 members=[m for c in cs for m in c.members]
 if len(members)!=len(set(members)):raise ValueError("source cannot appear in multiple clusters")
 if len(qs)!=len(members):raise ValueError("quality score must exist per source")
 vals=qs+(min_quality,)
 if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or not 0<=x<=1 for x in vals):raise ValueError("quality scores must be finite probabilities")
 roots={(c.owner,c.lineage_root) for c in cs};total=len(members);ok=bool(qs) and min(qs)>=min_quality
 return EvidenceIndependence(len(roots),total),DiversityScore((len(roots)/total if total else 0) if ok else 0,ok)
