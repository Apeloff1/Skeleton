"""Data health and retrieval lifecycle contracts VOL-349..354."""
from dataclasses import dataclass
from enum import Enum
@dataclass(frozen=True,slots=True)
class FreshnessSLI: source_watermark:int; observed_watermark:int; maximum_lag:int
    @property
    def healthy(self):return self.source_watermark-self.observed_watermark<=self.maximum_lag
@dataclass(frozen=True,slots=True)
class DataSLO: availability_target:float; correctness_target:float; freshness:FreshnessSLI
@dataclass(frozen=True,slots=True)
class DataServiceHealth: availability_ok:bool; correctness_ok:bool; freshness_ok:bool
    @property
    def healthy(self):return self.availability_ok and self.correctness_ok and self.freshness_ok
def data_health(slo,availability,correctness):return DataServiceHealth(availability>=slo.availability_target,correctness>=slo.correctness_target,slo.freshness.healthy)
@dataclass(frozen=True,slots=True)
class EmbeddingVersion: model:str; version:str; dimension:int; preprocessing:str
@dataclass(frozen=True,slots=True)
class EmbeddingRecord: record_id:str; embedding:EmbeddingVersion; vector:tuple[float,...]
    def __post_init__(self):
  if len(self.vector)!=self.embedding.dimension:raise ValueError("embedding dimension mismatch")
@dataclass(frozen=True,slots=True)
class EmbeddingMigration: source:EmbeddingVersion; target:EmbeddingVersion; validated:bool
def comparable(a,b):return a.embedding==b.embedding
@dataclass(frozen=True,slots=True)
class VectorIndexVersion: index_id:str; version:str; embedding:EmbeddingVersion; shadow:bool
@dataclass(frozen=True,slots=True)
class IndexValidation: recall_ok:bool; quality_ok:bool; freshness_ok:bool
@dataclass(frozen=True,slots=True)
class IndexMigration: active:VectorIndexVersion; shadow:VectorIndexVersion; validation:IndexValidation
def promote_index(m):
 if not m.shadow.shadow or not all((m.validation.recall_ok,m.validation.quality_ok,m.validation.freshness_ok)):return m.active
 return VectorIndexVersion(m.shadow.index_id,m.shadow.version,m.shadow.embedding,False)
@dataclass(frozen=True,slots=True)
class IndexWatermark: source_version:str; source_watermark:int
@dataclass(frozen=True,slots=True)
class SearchIndex: index_id:str; watermark:IndexWatermark; derived:bool=True
@dataclass(frozen=True,slots=True)
class IndexLifecycle: index:SearchIndex; rebuildable:bool; retired:bool=False
def retire_index(l):return IndexLifecycle(l.index,l.rebuildable,True) if l.rebuildable else l
class FreshnessState(str,Enum): FRESH="fresh"; STALE="stale"; UNKNOWN="unknown"
class StaleAction(str,Enum): REFRESH="refresh"; QUALIFY="qualify"; ABSTAIN="abstain"
@dataclass(frozen=True,slots=True)
class FreshnessRequirement: maximum_lag:int; stale_action:StaleAction
@dataclass(frozen=True,slots=True)
class FreshnessDecision: state:FreshnessState; action:StaleAction|None
def freshness(req,source_watermark,evidence_watermark):
 if source_watermark is None or evidence_watermark is None:return FreshnessDecision(FreshnessState.UNKNOWN,StaleAction.ABSTAIN)
 if source_watermark-evidence_watermark<=req.maximum_lag:return FreshnessDecision(FreshnessState.FRESH,None)
 return FreshnessDecision(FreshnessState.STALE,req.stale_action)
@dataclass(frozen=True,slots=True)
class SourceIdentity: source_id:str; owner:str; lineage:str
@dataclass(frozen=True,slots=True)
class TrustEvidence: evidence_id:str; claim_scope:str; domain:str; valid_until:int
@dataclass(frozen=True,slots=True)
class SourceTrust: identity:SourceIdentity; evidence:tuple[TrustEvidence,...]; trusted_for_instruction:bool=False
def trust_for(t,claim_scope,domain,now):
 return any(e.claim_scope==claim_scope and e.domain==domain and now<=e.valid_until for e in t.evidence)
def content_role(t,claim_scope,domain,now):return "data" if not trust_for(t,claim_scope,domain,now) else "evidence"
