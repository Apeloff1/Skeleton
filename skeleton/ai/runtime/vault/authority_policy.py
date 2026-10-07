"""Versioned deny-by-default authority policy compiler for VOL-028.

The module is non-executing. It compiles a small deterministic policy language
into immutable policy objects and evaluates user, service, and agent principals
through one contract. A positive decision is evidence only; it never executes a
tool or mutates durable state.

Grammar (one statement per line):

    policy <policy-id> version <positive-int> default deny
    allow <rule-id> <user|service|agent> <capability> <scope> approval <required|none>
    deny  <rule-id> <user|service|agent> <capability> <scope>

Matching is exact. There are intentionally no wildcards.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import math
import re
from typing import Any

from skeleton.contracts.canonical import canonical_json_bytes


AUTHORITY_POLICY_SCHEMA_VERSION = 1
AUTHORITY_POLICY_TASK_ID = "VOL-028"
AUTHORITY_POLICY_ACCOUNTABILITY_ID = "ACC-VOL-028"
_MAX_RULES = 1024
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,191}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class AuthorityPolicyError(ValueError):
    """Authority policy source or evaluation input is malformed."""


class PrincipalKind(str, Enum):
    USER = "user"
    SERVICE = "service"
    AGENT = "agent"


class PolicyEffect(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise AuthorityPolicyError(f"{field} must be a canonical token")
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise AuthorityPolicyError(f"{field} must be a positive integer")
    return value


def _tokens(values: tuple[str, ...], field: str) -> tuple[str, ...]:
    if not isinstance(values, tuple) or not values:
        raise AuthorityPolicyError(f"{field} must be a non-empty tuple")
    normalized = tuple(sorted(_token(value, field) for value in values))
    if len(normalized) != len(set(normalized)):
        raise AuthorityPolicyError(f"{field} must be unique")
    return normalized


def _finite_positive(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AuthorityPolicyError(f"{field} must be positive finite numeric")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise AuthorityPolicyError(f"{field} must be positive finite numeric")
    return result


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise AuthorityPolicyError(f"{field} must be lowercase sha256")
    return value


@dataclass(frozen=True, slots=True)
class AuthorityPrincipal:
    principal_id: str
    kind: PrincipalKind | str
    tenant_id: str
    generation: int
    capabilities: tuple[str, ...]
    scopes: tuple[str, ...]
    expires_at: float
    revoked: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "principal_id",
            _token(self.principal_id, "principal_id"),
        )
        try:
            kind = PrincipalKind(self.kind)
        except ValueError as exc:
            raise AuthorityPolicyError("invalid principal kind") from exc
        object.__setattr__(self, "kind", kind)
        object.__setattr__(
            self,
            "tenant_id",
            _token(self.tenant_id, "tenant_id"),
        )
        object.__setattr__(
            self,
            "generation",
            _positive_int(self.generation, "generation"),
        )
        object.__setattr__(
            self,
            "capabilities",
            _tokens(self.capabilities, "capabilities"),
        )
        object.__setattr__(
            self,
            "scopes",
            _tokens(self.scopes, "scopes"),
        )
        object.__setattr__(
            self,
            "expires_at",
            _finite_positive(self.expires_at, "expires_at"),
        )
        if not isinstance(self.revoked, bool):
            raise AuthorityPolicyError("revoked must be boolean")

    def payload(self) -> dict[str, Any]:
        return {
            "principal_id": self.principal_id,
            "kind": self.kind.value,
            "tenant_id": self.tenant_id,
            "generation": self.generation,
            "capabilities": list(self.capabilities),
            "scopes": list(self.scopes),
            "expires_at": self.expires_at,
            "revoked": self.revoked,
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.payload())).hexdigest()


@dataclass(frozen=True, slots=True)
class AuthorityRequest:
    principal_id: str
    tenant_id: str
    capability: str
    scope: str
    operation_id: str
    requested_generation: int

    def __post_init__(self) -> None:
        for field in (
            "principal_id",
            "tenant_id",
            "capability",
            "scope",
            "operation_id",
        ):
            object.__setattr__(
                self,
                field,
                _token(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "requested_generation",
            _positive_int(self.requested_generation, "requested_generation"),
        )

    def payload(self) -> dict[str, Any]:
        return {
            "principal_id": self.principal_id,
            "tenant_id": self.tenant_id,
            "capability": self.capability,
            "scope": self.scope,
            "operation_id": self.operation_id,
            "requested_generation": self.requested_generation,
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.payload())).hexdigest()


@dataclass(frozen=True, slots=True)
class AuthorityPolicyRule:
    rule_id: str
    effect: PolicyEffect | str
    principal_kind: PrincipalKind | str
    capability: str
    scope: str
    approval_required: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_id", _token(self.rule_id, "rule_id"))
        try:
            effect = PolicyEffect(self.effect)
            kind = PrincipalKind(self.principal_kind)
        except ValueError as exc:
            raise AuthorityPolicyError("invalid rule enum") from exc
        object.__setattr__(self, "effect", effect)
        object.__setattr__(self, "principal_kind", kind)
        object.__setattr__(
            self,
            "capability",
            _token(self.capability, "capability"),
        )
        object.__setattr__(self, "scope", _token(self.scope, "scope"))
        if not isinstance(self.approval_required, bool):
            raise AuthorityPolicyError("approval_required must be boolean")
        if effect is PolicyEffect.DENY and self.approval_required:
            raise AuthorityPolicyError("deny rules cannot require approval")

    def payload(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "effect": self.effect.value,
            "principal_kind": self.principal_kind.value,
            "capability": self.capability,
            "scope": self.scope,
            "approval_required": self.approval_required,
        }


@dataclass(frozen=True, slots=True)
class CompiledAuthorityPolicy:
    policy_id: str
    version: int
    rules: tuple[AuthorityPolicyRule, ...]
    source_digest: str
    default_effect: PolicyEffect = PolicyEffect.DENY
    schema_version: int = AUTHORITY_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "policy_id",
            _token(self.policy_id, "policy_id"),
        )
        object.__setattr__(
            self,
            "version",
            _positive_int(self.version, "version"),
        )
        if self.default_effect is not PolicyEffect.DENY:
            raise AuthorityPolicyError("policy default must be deny")
        if (
            not isinstance(self.rules, tuple)
            or not self.rules
            or len(self.rules) > _MAX_RULES
        ):
            raise AuthorityPolicyError("rules must be a bounded non-empty tuple")
        if any(not isinstance(rule, AuthorityPolicyRule) for rule in self.rules):
            raise AuthorityPolicyError("rules must contain AuthorityPolicyRule")
        ids = [rule.rule_id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise AuthorityPolicyError("duplicate policy rule id")
        semantic_keys = [
            (
                rule.effect.value,
                rule.principal_kind.value,
                rule.capability,
                rule.scope,
                rule.approval_required,
            )
            for rule in self.rules
        ]
        if len(semantic_keys) != len(set(semantic_keys)):
            raise AuthorityPolicyError("duplicate semantic policy rule")
        object.__setattr__(
            self,
            "rules",
            tuple(sorted(self.rules, key=lambda rule: rule.rule_id)),
        )
        object.__setattr__(
            self,
            "source_digest",
            _sha(self.source_digest, "source_digest"),
        )
        if self.schema_version != AUTHORITY_POLICY_SCHEMA_VERSION:
            raise AuthorityPolicyError("unsupported policy schema version")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": AUTHORITY_POLICY_TASK_ID,
            "accountability_id": AUTHORITY_POLICY_ACCOUNTABILITY_ID,
            "policy_id": self.policy_id,
            "version": self.version,
            "default_effect": self.default_effect.value,
            "source_digest": self.source_digest,
            "rules": [rule.payload() for rule in self.rules],
            "production_authority": False,
        }

    @property
    def policy_digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.payload())).hexdigest()


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    reasons: tuple[str, ...]
    policy_id: str
    policy_version: int
    policy_digest: str
    principal_digest: str
    request_digest: str
    matched_rule_ids: tuple[str, ...]
    approval_required: bool
    approval_ref_digest: str | None
    authority_scope: str = "authority-decision-only"
    production_authority: bool = False
    schema_version: int = AUTHORITY_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.allowed, bool):
            raise AuthorityPolicyError("allowed must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(reason, str) or not reason
            for reason in self.reasons
        ):
            raise AuthorityPolicyError("reasons must contain non-empty strings")
        object.__setattr__(self, "policy_id", _token(self.policy_id, "policy_id"))
        object.__setattr__(
            self,
            "policy_version",
            _positive_int(self.policy_version, "policy_version"),
        )
        for field in ("policy_digest", "principal_digest", "request_digest"):
            object.__setattr__(self, field, _sha(getattr(self, field), field))
        if not isinstance(self.matched_rule_ids, tuple):
            raise AuthorityPolicyError("matched_rule_ids must be tuple")
        matched = tuple(
            sorted(_token(rule_id, "matched_rule_ids") for rule_id in self.matched_rule_ids)
        )
        if len(matched) != len(set(matched)):
            raise AuthorityPolicyError("matched_rule_ids must be unique")
        object.__setattr__(self, "matched_rule_ids", matched)
        if not isinstance(self.approval_required, bool):
            raise AuthorityPolicyError("approval_required must be boolean")
        if self.approval_ref_digest is not None:
            object.__setattr__(
                self,
                "approval_ref_digest",
                _sha(self.approval_ref_digest, "approval_ref_digest"),
            )
        if self.authority_scope != "authority-decision-only":
            raise AuthorityPolicyError("authority scope escalation")
        if self.production_authority is not False:
            raise AuthorityPolicyError("policy decision cannot execute production")
        if self.schema_version != AUTHORITY_POLICY_SCHEMA_VERSION:
            raise AuthorityPolicyError("unsupported decision schema version")
        if self.allowed and self.reasons:
            raise AuthorityPolicyError("allowed decision cannot carry denial reasons")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "allowed": self.allowed,
            "reasons": list(self.reasons),
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "policy_digest": self.policy_digest,
            "principal_digest": self.principal_digest,
            "request_digest": self.request_digest,
            "matched_rule_ids": list(self.matched_rule_ids),
            "approval_required": self.approval_required,
            "approval_ref_digest": self.approval_ref_digest,
            "authority_scope": self.authority_scope,
            "production_authority": self.production_authority,
        }

    @property
    def decision_digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.payload())).hexdigest()


def compile_authority_policy(source: str) -> CompiledAuthorityPolicy:
    if not isinstance(source, str) or not source.strip():
        raise AuthorityPolicyError("policy source must be non-empty")
    normalized_lines = tuple(
        line.strip()
        for line in source.splitlines()
        if line.strip() and not line.strip().startswith("#")
    )
    if not normalized_lines:
        raise AuthorityPolicyError("policy source has no statements")
    header = normalized_lines[0].split()
    if (
        len(header) != 6
        or header[0] != "policy"
        or header[2] != "version"
        or header[4] != "default"
        or header[5] != "deny"
    ):
        raise AuthorityPolicyError("invalid policy header")
    policy_id = _token(header[1], "policy_id")
    try:
        version = int(header[3])
    except ValueError as exc:
        raise AuthorityPolicyError("policy version must be integer") from exc
    version = _positive_int(version, "version")

    rules: list[AuthorityPolicyRule] = []
    for line in normalized_lines[1:]:
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "allow":
            if (
                len(parts) != 7
                or parts[5] != "approval"
                or parts[6] not in {"required", "none"}
            ):
                raise AuthorityPolicyError("invalid allow rule")
            rule = AuthorityPolicyRule(
                rule_id=parts[1],
                effect=PolicyEffect.ALLOW,
                principal_kind=parts[2],
                capability=parts[3],
                scope=parts[4],
                approval_required=parts[6] == "required",
            )
        elif parts[0] == "deny":
            if len(parts) != 5:
                raise AuthorityPolicyError("invalid deny rule")
            rule = AuthorityPolicyRule(
                rule_id=parts[1],
                effect=PolicyEffect.DENY,
                principal_kind=parts[2],
                capability=parts[3],
                scope=parts[4],
            )
        else:
            raise AuthorityPolicyError("unknown policy statement")
        rules.append(rule)
        if len(rules) > _MAX_RULES:
            raise AuthorityPolicyError("policy rule limit exceeded")
    if not rules:
        raise AuthorityPolicyError("policy must contain at least one rule")

    normalized_source = "\n".join(normalized_lines) + "\n"
    source_digest = hashlib.sha256(normalized_source.encode("utf-8")).hexdigest()
    return CompiledAuthorityPolicy(
        policy_id=policy_id,
        version=version,
        rules=tuple(rules),
        source_digest=source_digest,
    )


def evaluate_authority(
    *,
    policy: CompiledAuthorityPolicy,
    principal: AuthorityPrincipal,
    request: AuthorityRequest,
    observed_at: float,
    approval_ref: str | None = None,
) -> PolicyDecision:
    if not isinstance(policy, CompiledAuthorityPolicy):
        raise TypeError("policy must be CompiledAuthorityPolicy")
    if not isinstance(principal, AuthorityPrincipal):
        raise TypeError("principal must be AuthorityPrincipal")
    if not isinstance(request, AuthorityRequest):
        raise TypeError("request must be AuthorityRequest")
    now = _finite_positive(observed_at, "observed_at")

    reasons: list[str] = []
    if principal.revoked:
        reasons.append("principal-revoked")
    if now >= principal.expires_at:
        reasons.append("principal-expired")
    if request.principal_id != principal.principal_id:
        reasons.append("principal-identity-mismatch")
    if request.tenant_id != principal.tenant_id:
        reasons.append("tenant-boundary-mismatch")
    if request.requested_generation != principal.generation:
        reasons.append("authority-generation-mismatch")
    if request.capability not in principal.capabilities:
        reasons.append("principal-capability-not-granted")
    if request.scope not in principal.scopes:
        reasons.append("principal-scope-not-granted")

    matching = tuple(
        rule
        for rule in policy.rules
        if rule.principal_kind is principal.kind
        and rule.capability == request.capability
        and rule.scope == request.scope
    )
    deny_rules = tuple(rule for rule in matching if rule.effect is PolicyEffect.DENY)
    allow_rules = tuple(rule for rule in matching if rule.effect is PolicyEffect.ALLOW)
    if deny_rules:
        reasons.append("explicit-deny")
    elif not allow_rules:
        reasons.append("default-deny")
    elif len(allow_rules) != 1:
        reasons.append("ambiguous-allow")
    approval_required = len(allow_rules) == 1 and allow_rules[0].approval_required
    approval_digest: str | None = None
    if approval_required:
        if approval_ref is None or not isinstance(approval_ref, str) or not approval_ref.strip():
            reasons.append("approval-required")
        else:
            normalized_approval = approval_ref.strip()
            approval_digest = hashlib.sha256(
                canonical_json_bytes(
                    {
                        "approval_ref": normalized_approval,
                        "principal_id": principal.principal_id,
                        "operation_id": request.operation_id,
                        "request_digest": request.digest,
                        "policy_digest": policy.policy_digest,
                    }
                )
            ).hexdigest()
    elif approval_ref is not None:
        if not isinstance(approval_ref, str) or not approval_ref.strip():
            reasons.append("approval-ref-invalid")
        else:
            approval_digest = hashlib.sha256(
                approval_ref.strip().encode("utf-8")
            ).hexdigest()

    normalized_reasons = tuple(sorted(set(reasons)))
    return PolicyDecision(
        allowed=not normalized_reasons,
        reasons=normalized_reasons,
        policy_id=policy.policy_id,
        policy_version=policy.version,
        policy_digest=policy.policy_digest,
        principal_digest=principal.digest,
        request_digest=request.digest,
        matched_rule_ids=tuple(rule.rule_id for rule in matching),
        approval_required=approval_required,
        approval_ref_digest=approval_digest,
    )


__all__ = [
    "AUTHORITY_POLICY_ACCOUNTABILITY_ID",
    "AUTHORITY_POLICY_SCHEMA_VERSION",
    "AUTHORITY_POLICY_TASK_ID",
    "AuthorityPolicyError",
    "AuthorityPolicyRule",
    "AuthorityPrincipal",
    "AuthorityRequest",
    "CompiledAuthorityPolicy",
    "PolicyDecision",
    "PolicyEffect",
    "PrincipalKind",
    "compile_authority_policy",
    "evaluate_authority",
]
