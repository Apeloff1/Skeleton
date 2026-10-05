"""Evidence bindings for component cards, health, providers, offline, and air-gap profiles.

VOL-221..VOL-230 build on the existing deferred runtime primitives in
research_evaluation.py and operations_experience.py.  This module binds those
primitives to exact evidence identities and fail-closed operational policy.
Nothing here grants deployment, promotion, or production authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from .contracts import sha256_json
from .operations_experience import DependencyHealth
from .research_evaluation import (
    ComponentCard,
    DeploymentProfile,
    HealthScore,
    ProviderFailover,
    ProviderRisk,
)


class ComponentProviderAssuranceError(ValueError):
    pass


_HEX=frozenset("0123456789abcdef")


def _text(name:str,value:object,*,limit:int=512)->str:
    if (
        not isinstance(value,str)
        or not value
        or value!=value.strip()
        or len(value)>limit
        or any(ord(ch)<32 for ch in value)
    ):
        raise ComponentProviderAssuranceError(
            f"{name} must be normalized non-empty text"
        )
    return value


def _texts(name:str,values:Iterable[str],*,allow_empty:bool=False)->tuple[str,...]:
    if isinstance(values,(str,bytes)):
        raise ComponentProviderAssuranceError(f"{name} must be a collection")
    result=tuple(sorted({_text(name,value) for value in values}))
    if not result and not allow_empty:
        raise ComponentProviderAssuranceError(f"{name} must be non-empty")
    return result


def _sha(name:str,value:object)->str:
    text=_text(name,value,limit=64)
    if len(text)!=64 or any(ch not in _HEX for ch in text):
        raise ComponentProviderAssuranceError(
            f"{name} must be lowercase sha256"
        )
    return text


def _integer(name:str,value:object,*,minimum:int=0)->int:
    if isinstance(value,bool) or not isinstance(value,int) or value<minimum:
        raise ComponentProviderAssuranceError(
            f"{name} must be integer >= {minimum}"
        )
    return value


def _unit(name:str,value:object)->float:
    if isinstance(value,bool) or not isinstance(value,(int,float)):
        raise ComponentProviderAssuranceError(f"{name} must be numeric")
    result=float(value)
    if not 0.0<=result<=1.0:
        raise ComponentProviderAssuranceError(f"{name} must be within [0,1]")
    return result


# VOL-221..224 ------------------------------------------------------------


@dataclass(frozen=True,slots=True)
class CardEvidence:
    card_kind:str
    component_id:str
    card_digest:str
    source_digests:tuple[str,...]
    security_review_digest:str|None=None
    performance_evidence_digest:str|None=None
    production_authority:bool=False

    def __post_init__(self)->None:
        if self.card_kind not in {"model","dataset","tool","agent"}:
            raise ComponentProviderAssuranceError("unsupported card kind")
        object.__setattr__(self,"component_id",_text("component_id",self.component_id))
        object.__setattr__(self,"card_digest",_sha("card_digest",self.card_digest))
        source=tuple(sorted(_sha("source_digest",value) for value in self.source_digests))
        if not source:
            raise ComponentProviderAssuranceError("card evidence requires source digests")
        object.__setattr__(self,"source_digests",source)
        if self.security_review_digest is not None:
            object.__setattr__(
                self,
                "security_review_digest",
                _sha("security_review_digest",self.security_review_digest),
            )
        if self.performance_evidence_digest is not None:
            object.__setattr__(
                self,
                "performance_evidence_digest",
                _sha("performance_evidence_digest",self.performance_evidence_digest),
            )
        if self.card_kind=="tool" and self.security_review_digest is None:
            raise ComponentProviderAssuranceError(
                "tool card requires security review evidence"
            )
        if self.card_kind=="agent" and self.performance_evidence_digest is None:
            raise ComponentProviderAssuranceError(
                "agent card requires performance evidence"
            )
        if self.production_authority is not False:
            raise ComponentProviderAssuranceError(
                "component card evidence cannot grant production authority"
            )

    @property
    def digest(self)->str:
        return sha256_json({
            "card_kind":self.card_kind,
            "component_id":self.component_id,
            "card_digest":self.card_digest,
            "source_digests":list(self.source_digests),
            "security_review_digest":self.security_review_digest,
            "performance_evidence_digest":self.performance_evidence_digest,
            "production_authority":False,
        })


def _card_digest(card:ComponentCard)->str:
    return sha256_json({
        "component_id":card.component_id,
        "version":card.version,
        "kind":card.kind,
        "artifact_digest":card.artifact_digest,
        "intended_use":card.intended_use,
        "limitations":list(card.limitations),
        "evidence_refs":list(card.evidence_refs),
    })


def build_model_card(
    *,
    component_id:str,
    version:str,
    artifact_digest:str,
    intended_use:str,
    limitations:Iterable[str],
    mbom_digest:str,
    evaluation_digests:Iterable[str],
)->tuple[ComponentCard,CardEvidence]:
    mbom=_sha("mbom_digest",mbom_digest)
    evals=tuple(_sha("evaluation_digest",value) for value in evaluation_digests)
    if not evals:
        raise ComponentProviderAssuranceError("model card requires evaluation evidence")
    refs=(f"mbom:{mbom}",)+tuple(f"eval:{value}" for value in sorted(evals))
    card=ComponentCard(
        _text("component_id",component_id),
        _text("version",version),
        "model",
        _sha("artifact_digest",artifact_digest),
        _text("intended_use",intended_use),
        _texts("limitation",limitations),
        refs,
    )
    return card,CardEvidence("model",card.component_id,_card_digest(card),(mbom,*evals))


def build_dataset_card(
    *,
    component_id:str,
    version:str,
    artifact_digest:str,
    intended_use:str,
    limitations:Iterable[str],
    dataset_registry_digest:str,
    lineage_digest:str,
)->tuple[ComponentCard,CardEvidence]:
    registry=_sha("dataset_registry_digest",dataset_registry_digest)
    lineage=_sha("lineage_digest",lineage_digest)
    card=ComponentCard(
        _text("component_id",component_id),
        _text("version",version),
        "dataset",
        _sha("artifact_digest",artifact_digest),
        _text("intended_use",intended_use),
        _texts("limitation",limitations),
        (f"dataset-registry:{registry}",f"lineage:{lineage}"),
    )
    return card,CardEvidence("dataset",card.component_id,_card_digest(card),(registry,lineage))


def build_tool_card(
    *,
    component_id:str,
    version:str,
    artifact_digest:str,
    intended_use:str,
    limitations:Iterable[str],
    tool_definition_digest:str,
    security_review_digest:str,
)->tuple[ComponentCard,CardEvidence]:
    definition=_sha("tool_definition_digest",tool_definition_digest)
    review=_sha("security_review_digest",security_review_digest)
    card=ComponentCard(
        _text("component_id",component_id),
        _text("version",version),
        "tool",
        _sha("artifact_digest",artifact_digest),
        _text("intended_use",intended_use),
        _texts("limitation",limitations),
        (f"tool-definition:{definition}",f"security-review:{review}"),
    )
    return card,CardEvidence(
        "tool",card.component_id,_card_digest(card),(definition,review),
        security_review_digest=review,
    )


def build_agent_card(
    *,
    component_id:str,
    version:str,
    artifact_digest:str,
    intended_use:str,
    limitations:Iterable[str],
    agent_registry_digest:str,
    performance_evidence_digest:str,
)->tuple[ComponentCard,CardEvidence]:
    registry=_sha("agent_registry_digest",agent_registry_digest)
    performance=_sha("performance_evidence_digest",performance_evidence_digest)
    card=ComponentCard(
        _text("component_id",component_id),
        _text("version",version),
        "agent",
        _sha("artifact_digest",artifact_digest),
        _text("intended_use",intended_use),
        _texts("limitation",limitations),
        (f"agent-registry:{registry}",f"performance:{performance}"),
    )
    return card,CardEvidence(
        "agent",card.component_id,_card_digest(card),(registry,performance),
        performance_evidence_digest=performance,
    )


# VOL-225 -----------------------------------------------------------------


@dataclass(frozen=True,slots=True)
class HealthEvidence:
    component_id:str
    score_digest:str
    reliability_evidence_digest:str
    security_evidence_digest:str
    freshness_evidence_digest:str
    dependency_evidence_digest:str
    dashboard_metric_id:str
    healthy:bool
    production_authority:bool=False

    def __post_init__(self)->None:
        object.__setattr__(self,"component_id",_text("component_id",self.component_id))
        for name in (
            "score_digest","reliability_evidence_digest","security_evidence_digest",
            "freshness_evidence_digest","dependency_evidence_digest",
        ):
            object.__setattr__(self,name,_sha(name,getattr(self,name)))
        object.__setattr__(
            self,"dashboard_metric_id",_text("dashboard_metric_id",self.dashboard_metric_id)
        )
        if not isinstance(self.healthy,bool):
            raise ComponentProviderAssuranceError("healthy must be boolean")
        if self.production_authority is not False:
            raise ComponentProviderAssuranceError(
                "health evidence cannot grant production authority"
            )


def build_health_score(
    *,
    component_id:str,
    reliability:float,
    security:float,
    freshness:float,
    dependency_health:float,
    reliability_evidence_digest:str,
    security_evidence_digest:str,
    freshness_evidence_digest:str,
    dependency_evidence_digest:str,
    healthy_threshold:float=0.8,
)->tuple[HealthScore,HealthEvidence]:
    score=HealthScore(
        _text("component_id",component_id),
        _unit("reliability",reliability),
        _unit("security",security),
        _unit("freshness",freshness),
        _unit("dependency_health",dependency_health),
    )
    threshold=_unit("healthy_threshold",healthy_threshold)
    score_digest=sha256_json({
        "component_id":score.component_id,
        "reliability":score.reliability,
        "security":score.security,
        "freshness":score.freshness,
        "dependency_health":score.dependency_health,
        "total":score.total,
    })
    evidence=HealthEvidence(
        score.component_id,
        score_digest,
        _sha("reliability_evidence_digest",reliability_evidence_digest),
        _sha("security_evidence_digest",security_evidence_digest),
        _sha("freshness_evidence_digest",freshness_evidence_digest),
        _sha("dependency_evidence_digest",dependency_evidence_digest),
        f"component.health.{score.component_id}",
        score.total>=threshold,
    )
    return score,evidence


# VOL-226 -----------------------------------------------------------------


@dataclass(frozen=True,slots=True)
class DependencyHealthEvidence:
    dependency_id:str
    dependency_digest:str
    sbom_digest:str
    healthy:bool
    backlog_ref:str|None
    blocker_codes:tuple[str,...]

    def __post_init__(self)->None:
        object.__setattr__(self,"dependency_id",_text("dependency_id",self.dependency_id))
        object.__setattr__(
            self,"dependency_digest",_sha("dependency_digest",self.dependency_digest)
        )
        object.__setattr__(self,"sbom_digest",_sha("sbom_digest",self.sbom_digest))
        if not isinstance(self.healthy,bool):
            raise ComponentProviderAssuranceError("healthy must be boolean")
        if self.backlog_ref is not None:
            object.__setattr__(self,"backlog_ref",_text("backlog_ref",self.backlog_ref))
        object.__setattr__(
            self,"blocker_codes",_texts("blocker_code",self.blocker_codes,allow_empty=True)
        )
        if self.healthy and (self.backlog_ref is not None or self.blocker_codes):
            raise ComponentProviderAssuranceError(
                "healthy dependency cannot carry blockers/backlog"
            )
        if not self.healthy and self.backlog_ref is None:
            raise ComponentProviderAssuranceError(
                "unhealthy dependency must bind backlog"
            )


def assess_dependency_health(
    dependency:DependencyHealth,
    *,
    sbom_digest:str,
    backlog_ref:str|None=None,
)->DependencyHealthEvidence:
    blockers=[]
    if dependency.vulnerability_count:
        blockers.append("known-vulnerability")
    if dependency.stale:
        blockers.append("stale")
    if not dependency.supported:
        blockers.append("unsupported")
    healthy=dependency.healthy
    bound_backlog=None if healthy else _text("backlog_ref",backlog_ref)
    digest=sha256_json({
        "dependency_id":dependency.dependency_id,
        "version":dependency.version,
        "vulnerability_count":dependency.vulnerability_count,
        "stale":dependency.stale,
        "supported":dependency.supported,
    })
    return DependencyHealthEvidence(
        dependency.dependency_id,digest,_sha("sbom_digest",sbom_digest),
        healthy,bound_backlog,tuple(sorted(blockers)),
    )


# VOL-227..228 ------------------------------------------------------------


@dataclass(frozen=True,slots=True)
class ProviderRiskEvidence:
    provider_digest:str
    dependency_digests:tuple[str,...]
    failover_class:str
    risk_acceptable:bool
    blockers:tuple[str,...]

    def __post_init__(self)->None:
        object.__setattr__(self,"provider_digest",_sha("provider_digest",self.provider_digest))
        dependencies=tuple(sorted(_sha("dependency_digest",value) for value in self.dependency_digests))
        if not dependencies:
            raise ComponentProviderAssuranceError("provider risk requires dependency map")
        object.__setattr__(self,"dependency_digests",dependencies)
        object.__setattr__(self,"failover_class",_text("failover_class",self.failover_class))
        if not isinstance(self.risk_acceptable,bool):
            raise ComponentProviderAssuranceError("risk_acceptable must be boolean")
        object.__setattr__(
            self,"blockers",_texts("blocker",self.blockers,allow_empty=True)
        )
        if self.risk_acceptable!=(not self.blockers):
            raise ComponentProviderAssuranceError(
                "provider risk state must match blockers"
            )


def assess_provider_risk(
    provider:ProviderRisk,
    *,
    dependency_digests:Iterable[str],
    failover_class:str,
    max_risk:float,
)->ProviderRiskEvidence:
    threshold=_unit("max_risk",max_risk)
    blockers=[]
    if not provider.available:
        blockers.append("provider-unavailable")
    if provider.risk_score>threshold:
        blockers.append("risk-above-policy")
    provider_digest=sha256_json({
        "provider_id":provider.provider_id,
        "risk_score":provider.risk_score,
        "data_classes":list(provider.data_classes),
        "regions":list(provider.regions),
        "available":provider.available,
    })
    return ProviderRiskEvidence(
        provider_digest,tuple(dependency_digests),_text("failover_class",failover_class),
        not blockers,tuple(sorted(blockers)),
    )


@dataclass(frozen=True,slots=True)
class ProviderFailoverDecision:
    selected_provider_id:str
    selected_provider_digest:str
    required_data_class:str
    compatibility_class:str
    reason_code:str
    production_authority:bool=False

    def __post_init__(self)->None:
        for name in (
            "selected_provider_id","required_data_class",
            "compatibility_class","reason_code",
        ):
            object.__setattr__(self,name,_text(name,getattr(self,name)))
        object.__setattr__(
            self,"selected_provider_digest",_sha("selected_provider_digest",self.selected_provider_digest)
        )
        if self.production_authority is not False:
            raise ComponentProviderAssuranceError(
                "failover decision evidence cannot grant production authority"
            )


def choose_provider_failover(
    providers:Sequence[ProviderRisk],
    *,
    required_data_class:str,
    allowed_regions:Iterable[str],
    max_risk:float,
    compatibility_classes:Mapping[str,str],
)->ProviderFailoverDecision:
    if set(compatibility_classes)!={item.provider_id for item in providers}:
        raise ComponentProviderAssuranceError(
            "provider compatibility map must cover exact provider inventory"
        )
    selected=ProviderFailover().choose(
        providers,
        required_data_class=_text("required_data_class",required_data_class),
        allowed_regions=_texts("allowed_region",allowed_regions),
        max_risk=_unit("max_risk",max_risk),
    )
    digest=sha256_json({
        "provider_id":selected.provider_id,
        "risk_score":selected.risk_score,
        "data_classes":list(selected.data_classes),
        "regions":list(selected.regions),
        "available":selected.available,
    })
    return ProviderFailoverDecision(
        selected.provider_id,digest,required_data_class,
        _text("compatibility_class",compatibility_classes[selected.provider_id]),
        "lowest-policy-compatible-risk",
    )


# VOL-229 -----------------------------------------------------------------


@dataclass(frozen=True,slots=True)
class OfflineCapability:
    capability_id:str
    local_model_required:bool
    local_storage_required:bool
    network_required:bool
    degraded_mode:str|None=None

    def __post_init__(self)->None:
        object.__setattr__(self,"capability_id",_text("capability_id",self.capability_id))
        for name in ("local_model_required","local_storage_required","network_required"):
            if not isinstance(getattr(self,name),bool):
                raise ComponentProviderAssuranceError(f"{name} must be boolean")
        if self.degraded_mode is not None:
            object.__setattr__(
                self,"degraded_mode",_text("degraded_mode",self.degraded_mode)
            )


@dataclass(frozen=True,slots=True)
class OfflineCapabilityDecision:
    profile_id:str
    available_capabilities:tuple[str,...]
    unavailable_capabilities:tuple[str,...]
    degraded_capabilities:tuple[str,...]
    network_access:bool=False
    production_authority:bool=False

    def __post_init__(self)->None:
        object.__setattr__(self,"profile_id",_text("profile_id",self.profile_id))
        for name in (
            "available_capabilities","unavailable_capabilities","degraded_capabilities"
        ):
            object.__setattr__(
                self,name,_texts(name,getattr(self,name),allow_empty=True)
            )
        if self.network_access is not False:
            raise ComponentProviderAssuranceError(
                "offline capability decision cannot enable network"
            )
        if self.production_authority is not False:
            raise ComponentProviderAssuranceError(
                "offline evidence cannot grant production authority"
            )


def evaluate_offline_capabilities(
    profile:DeploymentProfile,
    capabilities:Sequence[OfflineCapability],
    *,
    local_model_present:bool,
    local_storage_present:bool,
)->OfflineCapabilityDecision:
    if profile.network_mode!="offline":
        raise ComponentProviderAssuranceError(
            "offline capability evaluation requires offline profile"
        )
    if profile.credential_mode=="hosted":
        raise ComponentProviderAssuranceError(
            "offline profile cannot depend on hosted credentials"
        )
    ids=[item.capability_id for item in capabilities]
    if not ids or len(ids)!=len(set(ids)):
        raise ComponentProviderAssuranceError(
            "offline capability identities must be unique and non-empty"
        )
    available=[]
    unavailable=[]
    degraded=[]
    for item in capabilities:
        missing=(
            item.network_required
            or (item.local_model_required and not local_model_present)
            or (item.local_storage_required and not local_storage_present)
        )
        if not missing:
            available.append(item.capability_id)
        elif item.degraded_mode is not None and not item.network_required:
            degraded.append(item.capability_id)
        else:
            unavailable.append(item.capability_id)
    return OfflineCapabilityDecision(
        profile.profile_id,tuple(available),tuple(unavailable),tuple(degraded)
    )


# VOL-230 -----------------------------------------------------------------


@dataclass(frozen=True,slots=True)
class AirGapPackage:
    package_id:str
    artifact_digests:tuple[str,...]
    sbom_digest:str
    signer_ids:tuple[str,...]
    signature_digests:tuple[str,...]
    trust_root_digest:str

    def __post_init__(self)->None:
        object.__setattr__(self,"package_id",_text("package_id",self.package_id))
        artifacts=tuple(sorted(_sha("artifact_digest",value) for value in self.artifact_digests))
        signers=_texts("signer_id",self.signer_ids)
        signatures=tuple(sorted(_sha("signature_digest",value) for value in self.signature_digests))
        if not artifacts:
            raise ComponentProviderAssuranceError("air-gap package requires artifacts")
        if len(signers)!=len(signatures):
            raise ComponentProviderAssuranceError(
                "air-gap signer/signature cardinality mismatch"
            )
        object.__setattr__(self,"artifact_digests",artifacts)
        object.__setattr__(self,"sbom_digest",_sha("sbom_digest",self.sbom_digest))
        object.__setattr__(self,"signer_ids",signers)
        object.__setattr__(self,"signature_digests",signatures)
        object.__setattr__(
            self,"trust_root_digest",_sha("trust_root_digest",self.trust_root_digest)
        )

    @property
    def digest(self)->str:
        return sha256_json({
            "package_id":self.package_id,
            "artifact_digests":list(self.artifact_digests),
            "sbom_digest":self.sbom_digest,
            "signer_ids":list(self.signer_ids),
            "signature_digests":list(self.signature_digests),
            "trust_root_digest":self.trust_root_digest,
        })


@dataclass(frozen=True,slots=True)
class AirGapInstallEvidence:
    package_digest:str
    profile_id:str
    trust_verified:bool
    install_passed:bool
    network_observed:bool
    hosted_credentials_observed:bool
    blockers:tuple[str,...]
    production_authority:bool=False

    def __post_init__(self)->None:
        object.__setattr__(self,"package_digest",_sha("package_digest",self.package_digest))
        object.__setattr__(self,"profile_id",_text("profile_id",self.profile_id))
        for name in (
            "trust_verified","install_passed","network_observed",
            "hosted_credentials_observed",
        ):
            if not isinstance(getattr(self,name),bool):
                raise ComponentProviderAssuranceError(f"{name} must be boolean")
        object.__setattr__(
            self,"blockers",_texts("blocker",self.blockers,allow_empty=True)
        )
        expected=(
            self.trust_verified
            and self.install_passed
            and not self.network_observed
            and not self.hosted_credentials_observed
        )
        if expected!=(not self.blockers):
            raise ComponentProviderAssuranceError(
                "air-gap install state must match blockers"
            )
        if self.production_authority is not False:
            raise ComponentProviderAssuranceError(
                "air-gap install evidence cannot grant production authority"
            )


def qualify_air_gap_install(
    profile:DeploymentProfile,
    package:AirGapPackage,
    *,
    expected_trust_root_digest:str,
    install_passed:bool,
    network_observed:bool=False,
    hosted_credentials_observed:bool=False,
)->AirGapInstallEvidence:
    if profile.network_mode!="air_gapped":
        raise ComponentProviderAssuranceError(
            "air-gap install qualification requires air_gapped profile"
        )
    if profile.credential_mode=="hosted":
        raise ComponentProviderAssuranceError(
            "air-gapped profile cannot use hosted credentials"
        )
    blockers=[]
    trust_verified=package.trust_root_digest==_sha(
        "expected_trust_root_digest",expected_trust_root_digest
    )
    if not trust_verified:
        blockers.append("trust-root-mismatch")
    if not install_passed:
        blockers.append("install-failed")
    if network_observed:
        blockers.append("network-observed")
    if hosted_credentials_observed:
        blockers.append("hosted-credentials-observed")
    return AirGapInstallEvidence(
        package.digest,profile.profile_id,trust_verified,bool(install_passed),
        bool(network_observed),bool(hosted_credentials_observed),
        tuple(sorted(blockers)),
    )


__all__=[
    "AirGapInstallEvidence","AirGapPackage","CardEvidence",
    "ComponentProviderAssuranceError","DependencyHealthEvidence","HealthEvidence",
    "OfflineCapability","OfflineCapabilityDecision","ProviderFailoverDecision",
    "ProviderRiskEvidence","assess_dependency_health","assess_provider_risk",
    "build_agent_card","build_dataset_card","build_health_score","build_model_card",
    "build_tool_card","choose_provider_failover","evaluate_offline_capabilities",
    "qualify_air_gap_install",
]
