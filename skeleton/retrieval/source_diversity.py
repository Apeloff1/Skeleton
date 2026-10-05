from dataclasses import dataclass
@dataclass(frozen=True)
class SourceCluster: cluster_id:str; members:tuple[str,...]; owner:str; lineage_root:str
@dataclass(frozen=True)
class EvidenceIndependence: independent_clusters:int; total_sources:int
@dataclass(frozen=True)
class DiversityScore: score:float; quality_floor_met:bool
def diversity(clusters,quality_scores,min_quality):
 roots={(c.owner,c.lineage_root) for c in clusters};total=sum(len(c.members) for c in clusters);ok=bool(quality_scores) and min(quality_scores)>=min_quality
 return EvidenceIndependence(len(roots),total),DiversityScore((len(roots)/total if total else 0) if ok else 0,ok)
