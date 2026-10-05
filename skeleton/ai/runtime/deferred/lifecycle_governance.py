"""Rights, research and lifecycle governance VOL-407,408,410-413,416-418."""
from dataclasses import dataclass
from enum import Enum
@dataclass(frozen=True,slots=True)
class LicenseObligation: name:str; required:bool
@dataclass(frozen=True,slots=True)
class LicenseRecord: artifact_id:str; version:str; license_id:str|None; provenance:str; obligations:tuple[LicenseObligation,...]
@dataclass(frozen=True,slots=True)
class LicenseCompatibility: compatible:bool; reason:str
def license_compatibility(records,distribution):
 if any(r.license_id is None for r in records):return LicenseCompatibility(False,"unknown license")
 if distribution and any(o.required and o.name=="no-redistribution" for r in records for o in r.obligations):return LicenseCompatibility(False,"distribution prohibited")
 return LicenseCompatibility(True,"compatible")
@dataclass(frozen=True,slots=True)
class UsageGrant: purpose:str; geography:frozenset[str]; retention_days:int; training:bool; evaluation:bool
@dataclass(frozen=True,slots=True)
class DataRights: dataset_id:str; grants:tuple[UsageGrant,...]; consent:bool
@dataclass(frozen=True,slots=True)
class RightsDecision: allowed:bool; reason:str
def rights_decision(r,purpose,geography,training=False,evaluation=False):
 if not r.dataset_id or not purpose or not geography:return RightsDecision(False,"identity absent")
 if any(g.retention_days<0 or not g.purpose or not g.geography for g in r.grants):return RightsDecision(False,"invalid grant")
 if not r.consent:return RightsDecision(False,"consent absent")
 ok=any(g.purpose==purpose and geography in g.geography and (not training or g.training) and (not evaluation or g.evaluation) for g in r.grants)
 return RightsDecision(ok,"granted" if ok else "purpose/geography/use denied")
@dataclass(frozen=True,slots=True)
class ResearchRisk: sensitive_human:bool; sensitive_data:bool; dual_use:bool
@dataclass(frozen=True,slots=True)
class EthicsReview: review_id:str; risk:ResearchRisk; consent_verified:bool; oversight_receipt:str|None
@dataclass(frozen=True,slots=True)
class EthicsDecision: approved:bool; reason:str
def ethics_decision(r):
 if not r.review_id:return EthicsDecision(False,"review identity absent")
 sensitive=any((r.risk.sensitive_human,r.risk.sensitive_data,r.risk.dual_use))
 return EthicsDecision((not sensitive) or (r.consent_verified and bool(r.oversight_receipt)),"review criteria")
class ModelState(str,Enum): INTAKE="intake"; EVALUATED="evaluated"; DEPLOYED="deployed"; RETIRED="retired"; ARCHIVED="archived"
@dataclass(frozen=True,slots=True)
class ModelGovernanceEvidence: evidence_id:str; owner:str; rollback:str; retention:str
@dataclass(frozen=True,slots=True)
class ModelTransition: source:ModelState; target:ModelState; evidence:ModelGovernanceEvidence
@dataclass(frozen=True,slots=True)
class ModelLifecycle: model_id:str; state:ModelState
def transition_model(m,t):
 if m.state!=t.source or not all((t.evidence.evidence_id,t.evidence.owner,t.evidence.rollback,t.evidence.retention)):raise ValueError("invalid transition evidence")
 return ModelLifecycle(m.model_id,t.target)
@dataclass(frozen=True,slots=True)
class ModelConsumer: consumer_id:str; migrated:bool
@dataclass(frozen=True,slots=True)
class ModelDeprecation: model_id:str; replacement:str; deadline:int; consumers:tuple[ModelConsumer,...]
@dataclass(frozen=True,slots=True)
class ModelRetirement: model_id:str; allowed:bool; exception_receipt:str|None=None
def retire_model(d,exception=None):return ModelRetirement(d.model_id,all(c.migrated for c in d.consumers) or bool(exception),exception)
@dataclass(frozen=True,slots=True)
class ProviderParity: capability:bool; policy:bool; quality:bool; cost:bool; data_boundary:bool
@dataclass(frozen=True,slots=True)
class ProviderMigration: source:str; target:str; parity:ProviderParity; shadow_passed:bool; rollback_ready:bool
@dataclass(frozen=True,slots=True)
class ProviderCutover: allowed:bool; reason:str
def provider_cutover(m):return ProviderCutover(all((m.parity.capability,m.parity.policy,m.parity.quality,m.parity.cost,m.parity.data_boundary,m.shadow_passed,m.rollback_ready)),"parity/shadow/rollback")
@dataclass(frozen=True,slots=True)
class ExperimentKillSwitch: enabled:bool
@dataclass(frozen=True,slots=True)
class ExperimentalFeature: feature_id:str; isolated:bool; production_claim:bool=False
@dataclass(frozen=True,slots=True)
class ExperimentExposure: feature:ExperimentalFeature; synthetic_or_shadow:bool; kill_switch:ExperimentKillSwitch
def experiment_allowed(e):return e.feature.isolated and e.synthetic_or_shadow and e.kill_switch.enabled and not e.feature.production_claim
@dataclass(frozen=True,slots=True)
class ResearchBranchPolicy: bounded_owners:frozenset[str]; production_gates_required:bool=True
@dataclass(frozen=True,slots=True)
class ResearchBranch: branch_id:str; parent:str; owner:str
@dataclass(frozen=True,slots=True)
class ResearchMergeCandidate: branch:ResearchBranch; lineage_preserved:bool; gates_passed:bool
def research_merge(c,p):return c.branch.owner in p.bounded_owners and c.lineage_preserved and c.gates_passed and p.production_gates_required
@dataclass(frozen=True,slots=True)
class Technique: technique_id:str; version:str
@dataclass(frozen=True,slots=True)
class RetirementEvidence: reason:str; replacement:str; consumers:tuple[str,...]; archive_location:str
@dataclass(frozen=True,slots=True)
class TechniqueRetirement: technique:Technique; evidence:RetirementEvidence
def retirement_complete(r):return all((r.evidence.reason,r.evidence.replacement,r.evidence.archive_location))
