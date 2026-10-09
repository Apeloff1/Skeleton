"""Executable threat-model coverage and change-impact triggers for VOL-026/VOL-167."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Iterable

from .contracts import SecurityContractError


_REQUIRED=frozenset({"tool-authority","secrets","filesystem","network-egress","supply-chain"})
_TRIGGER_DOMAINS=frozenset({"authority","data","network","identity","storage","supply-chain"})


def _text(name: str, value: object) -> str:
    if not isinstance(value,str) or not value or value != value.strip() or len(value)>512:
        raise SecurityContractError(f"invalid {name}")
    return value


@dataclass(frozen=True,slots=True)
class Threat:
    threat_id: str
    asset: str
    boundary: str
    mitigation: str
    validation: str

    def __post_init__(self) -> None:
        for name in ("threat_id","asset","boundary","mitigation","validation"):
            object.__setattr__(self,name,_text(name,getattr(self,name)))


@dataclass(frozen=True,slots=True)
class ThreatImpactTrigger:
    trigger_id: str
    domains: tuple[str,...]
    rationale: str

    def __post_init__(self) -> None:
        object.__setattr__(self,"trigger_id",_text("trigger_id",self.trigger_id))
        object.__setattr__(self,"rationale",_text("rationale",self.rationale))
        domains=tuple(sorted({_text("domain",value) for value in self.domains}))
        if not domains:
            raise SecurityContractError("threat impact trigger domains required")
        unknown=set(domains)-_TRIGGER_DOMAINS
        if unknown:
            raise SecurityContractError("unknown threat impact domains: "+",".join(sorted(unknown)))
        object.__setattr__(self,"domains",domains)


_DEFAULT_IMPACT_TRIGGERS=(
    ThreatImpactTrigger("TR-AUTH",("authority","identity"),"authorization or identity boundary changed"),
    ThreatImpactTrigger("TR-DATA",("data","storage"),"data classification, persistence, or lifecycle boundary changed"),
    ThreatImpactTrigger("TR-NET",("network",),"network or egress boundary changed"),
    ThreatImpactTrigger("TR-SUPPLY",("supply-chain",),"dependency, build, or artifact provenance changed"),
)

@dataclass(frozen=True,slots=True)
class ThreatModel:
    threats: tuple[Threat,...]
    model_version: str="vol026-v2"
    impact_triggers: tuple[ThreatImpactTrigger,...]=_DEFAULT_IMPACT_TRIGGERS

    def __post_init__(self) -> None:
        if not isinstance(self.threats,tuple) or not self.threats:
            raise SecurityContractError("threats required")
        ids=[item.threat_id for item in self.threats]
        if len(ids)!=len(set(ids)):
            raise SecurityContractError("duplicate threat id")
        assets={item.asset for item in self.threats}
        missing=_REQUIRED-assets
        if missing:
            raise SecurityContractError("missing required threat coverage: "+",".join(sorted(missing)))
        triggers=tuple(self.impact_triggers)
        trigger_ids=[item.trigger_id for item in triggers]
        if len(trigger_ids)!=len(set(trigger_ids)):
            raise SecurityContractError("duplicate threat impact trigger id")
        covered_domains=set().union(*(set(item.domains) for item in triggers)) if triggers else set()
        uncovered=_TRIGGER_DOMAINS-covered_domains
        if uncovered:
            raise SecurityContractError("missing threat impact trigger coverage: "+",".join(sorted(uncovered)))
        object.__setattr__(self,"threats",tuple(sorted(self.threats,key=lambda item:item.threat_id)))
        object.__setattr__(self,"impact_triggers",tuple(sorted(triggers,key=lambda item:item.trigger_id)))
        object.__setattr__(self,"model_version",_text("model_version",self.model_version))

    @property
    def digest(self) -> str:
        payload={
            "version":self.model_version,
            "threats":[
                {
                    "id":item.threat_id,
                    "asset":item.asset,
                    "boundary":item.boundary,
                    "mitigation":item.mitigation,
                    "validation":item.validation,
                }
                for item in self.threats
            ],
            "impact_triggers":[
                {
                    "id":item.trigger_id,
                    "domains":list(item.domains),
                    "rationale":item.rationale,
                }
                for item in self.impact_triggers
            ],
        }
        return sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()

    def review_required(self, changed_domains: Iterable[str]) -> bool:
        if isinstance(changed_domains,(str,bytes)):
            raise SecurityContractError("changed_domains must be a collection")
        changed={_text("changed_domain",value) for value in changed_domains}
        unknown=changed-_TRIGGER_DOMAINS
        if unknown:
            raise SecurityContractError("unknown changed threat domains: "+",".join(sorted(unknown)))
        return any(changed.intersection(trigger.domains) for trigger in self.impact_triggers)


def canonical_vol026_threat_model()->ThreatModel:
    return ThreatModel((
        Threat("T-AUTH-001","tool-authority","planner-to-tool","exact capability/resource/operation grant","skeleton/testing/test_vol026_capability_security.py"),
        Threat("T-SECRET-001","secrets","secret-store-to-runtime","reference-only SecretRef","skeleton/testing/test_secret_security.py"),
        Threat("T-FS-001","filesystem","input-to-rooted-filesystem","rooted path and archive sandbox enforcement","skeleton/testing/test_security_rooted_fs.py"),
        Threat("T-NET-001","network-egress","runtime-to-network","resolved destination plus connected-peer validation","skeleton/testing/test_security_outbound_http.py"),
        Threat("T-SUPPLY-001","supply-chain","dependency-to-runtime","artifact-bound SBOM and dependency integrity controls","skeleton/testing/test_sbom.py"),
    ))
