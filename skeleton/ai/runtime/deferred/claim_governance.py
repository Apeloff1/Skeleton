"""Source diversity and claim lifecycle contracts VOL-355..360."""
from dataclasses import dataclass
from enum import Enum
from .contracts import sha256_json
@dataclass(frozen=True,slots=True)
class EvidenceIndependence: source_id:str; lineage:str; owner:str; citations:frozenset[str]; quality:float
@dataclass(frozen=True,slots=True)
class SourceCluster: cluster_id:str; members:tuple[EvidenceIndependence,...]
@dataclass(frozen=True,slots=True)
class DiversityScore: independent_clusters:int; quality_floor:float; admissible:bool
def diversity(evidence,quality_floor):
 groups={(e.lineage,e.owner,tuple(sorted(e.citations))) for e in evidence}
 return DiversityScore(len(groups),quality_floor,bool(evidence) and all(e.quality>=quality_floor for e in evidence))
@dataclass(frozen=True,slots=True)
class ScopeDimension: name:str; value:str
@dataclass(frozen=True,slots=True)
class ClaimScope: dimensions:tuple[ScopeDimension,...]; valid_from:int; valid_to:int|None
@dataclass(frozen=True,slots=True)
class ScopeCompatibility: compatible:bool; qualification:str|None=None
def scope_compatibility(a,b):
 same=dict((x.name,x.value) for x in a.dimensions)==dict((x.name,x.value) for x in b.dimensions)
 overlap=(a.valid_to is None or a.valid_to>=b.valid_from) and (b.valid_to is None or b.valid_to>=a.valid_from)
 return ScopeCompatibility(same and overlap,None if same and overlap else "scope/time mismatch")
@dataclass(frozen=True,slots=True)
class ClaimFingerprint: normalized_text:str; scope:ClaimScope
@dataclass(frozen=True,slots=True)
class ClaimCluster: canonical:ClaimFingerprint; originals:tuple[str,...]
@dataclass(frozen=True,slots=True)
class ClaimMerge: cluster:ClaimCluster; lineage:tuple[str,...]
def merge_claims(items):
 if not items:raise ValueError("claims required")
 base=items[0][1]
 if any(x[1].normalized_text!=base.normalized_text or not scope_compatibility(base.scope,x[1].scope).compatible for x in items[1:]):raise ValueError("incompatible claims")
 ids=tuple(x[0] for x in items);return ClaimMerge(ClaimCluster(base,ids),ids)
class ClaimValidity(str,Enum): CURRENT="current"; STALE="stale"
@dataclass(frozen=True,slots=True)
class ExpirationPolicy: normal_ttl:int; volatile_ttl:int
@dataclass(frozen=True,slots=True)
class RevalidationRequest: claim_id:str; prior_evidence:tuple[str,...]
def claim_validity(observed_at,now,policy,volatile):return ClaimValidity.CURRENT if now-observed_at<=(policy.volatile_ttl if volatile else policy.normal_ttl) else ClaimValidity.STALE
@dataclass(frozen=True,slots=True)
class KnowledgeConflict: claim_ids:tuple[str,...]; evidence_ids:tuple[str,...]
@dataclass(frozen=True,slots=True)
class ReconciliationCase: case_id:str; conflict:KnowledgeConflict
@dataclass(frozen=True,slots=True)
class ReconciliationDecision: case_id:str; resolved_claim_id:str|None; rule:str|None; competing_evidence:tuple[str,...]
def reconcile(case,resolved_claim_id=None,rule=None):
 if resolved_claim_id is not None and (resolved_claim_id not in case.conflict.claim_ids or not rule):raise ValueError("resolution requires justified rule")
 return ReconciliationDecision(case.case_id,resolved_claim_id,rule,case.conflict.evidence_ids)
@dataclass(frozen=True,slots=True)
class KnowledgeSnapshot:
 source_watermark:str; index_watermark:str; model_version:str; schema_version:str
 @property
 def digest(self):return sha256_json({"source":self.source_watermark,"index":self.index_watermark,"model":self.model_version,"schema":self.schema_version})
@dataclass(frozen=True,slots=True)
class KnowledgeSnapshotDigest: digest:str
@dataclass(frozen=True,slots=True)
class KnowledgeDiff: changed:tuple[str,...]
def restore_allowed(snapshot,current_source_watermark):return snapshot.source_watermark==current_source_watermark
