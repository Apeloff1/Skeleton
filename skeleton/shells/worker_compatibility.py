"""Worker protocol and feature compatibility negotiation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from skeleton.shells.worker_identity import WorkerIdentity


@dataclass(frozen=True)
class CompatibilityRequirement:
    min_protocol_version:int=1
    max_protocol_version:int=1
    required_features:frozenset[str]=frozenset()
    forbidden_features:frozenset[str]=frozenset()

    def __post_init__(self)->None:
        if self.min_protocol_version<=0 or self.max_protocol_version<self.min_protocol_version:
            raise ValueError("invalid protocol version range")
        object.__setattr__(self,"required_features",frozenset(self.required_features))
        object.__setattr__(self,"forbidden_features",frozenset(self.forbidden_features))
        if self.required_features & self.forbidden_features:
            raise ValueError("features cannot be both required and forbidden")


@dataclass(frozen=True)
class CompatibilityResult:
    compatible:bool
    reasons:tuple[str,...]
    negotiated_protocol:int|None
    common_features:frozenset[str]

    def to_dict(self)->dict[str,object]:
        return {
            "compatible":self.compatible,
            "reasons":list(self.reasons),
            "negotiated_protocol":self.negotiated_protocol,
            "common_features":sorted(self.common_features),
        }


class WorkerCompatibility:
    def check(
        self,
        identity:WorkerIdentity,
        requirement:CompatibilityRequirement|None=None,
        *,
        controller_features:Iterable[str]=(),
        controller_protocol_version:int=1,
    )->CompatibilityResult:
        requirement=requirement or CompatibilityRequirement()
        reasons=[]
        protocol=identity.protocol_version
        if protocol<requirement.min_protocol_version or protocol>requirement.max_protocol_version:
            reasons.append("worker protocol outside required range")
        if protocol!=controller_protocol_version:
            reasons.append("controller/worker protocol mismatch")
        missing=requirement.required_features-identity.features
        if missing:reasons.append("worker missing required features")
        forbidden=requirement.forbidden_features & identity.features
        if forbidden:reasons.append("worker exposes forbidden features")
        common=frozenset(controller_features) & identity.features
        return CompatibilityResult(
            compatible=not reasons,
            reasons=tuple(reasons),
            negotiated_protocol=None if reasons else protocol,
            common_features=common,
        )
