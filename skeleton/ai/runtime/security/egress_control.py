"""Deterministic outbound egress policy for VOL-172.

This module does not open sockets. It combines declared destination policy with
the resolved-destination evidence produced by outbound_url.py.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable

from .outbound_url import ResolvedDestination, resolve_public_https_url, validate_public_https_url


class EgressControlError(ValueError):
    """Egress policy or decision evidence is malformed."""


def _token(name: str, value: object) -> str:
    if not isinstance(value,str) or not value or value != value.strip() or len(value)>512:
        raise EgressControlError(f"{name} must be non-empty normalized text")
    return value


def _tokens(name: str, values: Iterable[str]) -> tuple[str,...]:
    if isinstance(values,(str,bytes)):
        raise EgressControlError(f"{name} must be a collection")
    result=tuple(sorted({_token(name,value).lower() for value in values}))
    if not result:
        raise EgressControlError(f"{name} must be non-empty")
    return result


def _digest(value: object) -> str:
    try:
        encoded=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)
    except (TypeError,ValueError) as exc:
        raise EgressControlError("egress evidence must be canonical JSON") from exc
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class EgressPolicy:
    policy_id: str
    allowed_hosts: tuple[str,...]
    allowed_purposes: tuple[str,...]
    require_https: bool=True
    default_action: str="deny"

    def __post_init__(self) -> None:
        object.__setattr__(self,"policy_id",_token("policy_id",self.policy_id))
        object.__setattr__(self,"allowed_hosts",_tokens("allowed_host",self.allowed_hosts))
        object.__setattr__(self,"allowed_purposes",_tokens("allowed_purpose",self.allowed_purposes))
        if self.require_https is not True:
            raise EgressControlError("privileged egress must require HTTPS")
        if self.default_action!="deny":
            raise EgressControlError("egress default action must be deny")

    @property
    def digest(self)->str:
        return _digest({
            "policy_id":self.policy_id,
            "allowed_hosts":list(self.allowed_hosts),
            "allowed_purposes":list(self.allowed_purposes),
            "require_https":True,
            "default_action":"deny",
        })


@dataclass(frozen=True, slots=True)
class EgressRequest:
    request_id: str
    url: str
    purpose: str
    subject_id: str

    def __post_init__(self) -> None:
        for name in ("request_id","url","purpose","subject_id"):
            object.__setattr__(self,name,_token(name,getattr(self,name)))

    @property
    def digest(self)->str:
        return _digest({
            "request_id":self.request_id,
            "url":self.url,
            "purpose":self.purpose,
            "subject_id":self.subject_id,
        })


@dataclass(frozen=True, slots=True)
class EgressDecision:
    policy_digest: str
    request_digest: str
    allowed: bool
    reason_code: str
    destination: ResolvedDestination | None=None

    def __post_init__(self) -> None:
        for name in ("policy_digest","request_digest"):
            value=getattr(self,name)
            if not isinstance(value,str) or len(value)!=64 or any(ch not in "0123456789abcdef" for ch in value):
                raise EgressControlError(f"{name} must be a lowercase sha256 digest")
        if not isinstance(self.allowed,bool):
            raise EgressControlError("allowed must be boolean")
        object.__setattr__(self,"reason_code",_token("reason_code",self.reason_code))
        if not self.allowed and self.destination is not None:
            raise EgressControlError("denied egress cannot retain destination authority")


def evaluate_egress(
    policy: EgressPolicy,
    request: EgressRequest,
    *,
    resolver,
) -> EgressDecision:
    """Resolve under SSRF controls, then compare exact host/purpose policy."""
    if request.purpose.lower() not in policy.allowed_purposes:
        return EgressDecision(policy.digest,request.digest,False,"purpose_denied")
    # Authenticate the destination against the explicit host allowlist before
    # any DNS query. Disallowed hosts must not reach the resolver at all.
    try:
        _, host = validate_public_https_url(request.url, purpose="egress request")
    except ValueError:
        return EgressDecision(policy.digest,request.digest,False,"destination_invalid")
    if host not in policy.allowed_hosts:
        return EgressDecision(policy.digest,request.digest,False,"host_denied")
    try:
        destination=resolve_public_https_url(
            request.url,
            purpose="egress request",
            resolver=resolver,
        )
    except ValueError:
        return EgressDecision(policy.digest,request.digest,False,"destination_invalid")
    return EgressDecision(policy.digest,request.digest,True,"authorized",destination)
