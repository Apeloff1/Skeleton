"""FLGB-05 defensive security, policy, privacy, and evidence contracts.

The primitives are fail-closed control decisions. They do not weaken existing
repository security owners and intentionally preserve the canonical tenant
isolation implementation in skeleton.security.tenant_isolation.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Any, Sequence

MAX_ID_CHARS = 256
MAX_RULES = 4096
MAX_LABELS = 1024
MAX_FINDINGS = 10000
MAX_SCORE_PPM = 1_000_000
MAX_TEXT_CHARS = 2_000_000

_SECRET_PATTERNS = (
    re.compile(r"(?i)\\b(?:api[_-]?key|access[_-]?token|secret|password)\\b\\s*[:=]\\s*['\"]?([A-Za-z0-9_\\-./+=]{12,})"),
    re.compile(r"\\bgh[pousr]_[A-Za-z0-9]{20,}\\b"),
)
_PII_PATTERNS = (
    ("email", re.compile(r"\\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}\\b", re.I)),
    ("phone", re.compile(r"(?<!\\d)\\+?\\d(?:[\\s().-]?\\d){7,14}(?!\\d)")),
)
_PROMPT_INJECTION_PATTERNS = (
    re.compile(r"(?i)\\bignore (?:all |the )?(?:previous|prior|system) instructions\\b"),
    re.compile(r"(?i)\\breveal (?:the )?(?:system|developer) prompt\\b"),
    re.compile(r"(?i)\\bdisable (?:safety|policy|guardrails?)\\b"),
)


class SecurityPlaneError(ValueError):
    """Fail-closed FLGB-05 contract error."""


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def require_id(value: str, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > MAX_ID_CHARS
        or any(ord(ch) < 32 for ch in value)
    ):
        raise SecurityPlaneError(f"invalid {name}")
    return value


def require_digest(value: str, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise SecurityPlaneError(f"invalid {name}")
    return value


def digest_json(value: Any) -> str:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SecurityPlaneError("value is not canonical-json encodable") from exc
    return sha256(encoded).hexdigest()


@dataclass(frozen=True)
class PolicyRule:
    rule_id: str
    effect: str
    action: str
    required_labels: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_id(self.rule_id, "rule_id")
        require_id(self.action, "action")
        if self.effect not in {"allow", "deny", "require-approval"}:
            raise SecurityPlaneError("invalid policy effect")
        labels = tuple(sorted(self.required_labels))
        if len(labels) > MAX_LABELS or len(set(labels)) != len(labels):
            raise SecurityPlaneError("invalid policy labels")
        for label in labels:
            require_id(label, "policy label")
        object.__setattr__(self, "required_labels", labels)


@dataclass(frozen=True)
class PolicyDecision:
    action: str
    effect: str
    matched_rule_ids: tuple[str, ...]
    reason: str

    @property
    def digest(self) -> str:
        return digest_json(self.__dict__)


def evaluate_policy(action: str, labels: Sequence[str], rules: Sequence[PolicyRule]) -> PolicyDecision:
    action = require_id(action, "action")
    subject_labels = set(labels)
    if len(subject_labels) != len(tuple(labels)) or len(subject_labels) > MAX_LABELS:
        raise SecurityPlaneError("invalid subject labels")
    for label in subject_labels:
        require_id(label, "subject label")
    if len(rules) > MAX_RULES:
        raise SecurityPlaneError("policy rule budget exceeded")
    matches = [
        rule
        for rule in rules
        if rule.action == action and set(rule.required_labels).issubset(subject_labels)
    ]
    if not matches:
        return PolicyDecision(action, "deny", (), "no-matching-allow")
    deny = sorted(rule.rule_id for rule in matches if rule.effect == "deny")
    if deny:
        return PolicyDecision(action, "deny", tuple(deny), "explicit-deny")
    approvals = sorted(rule.rule_id for rule in matches if rule.effect == "require-approval")
    if approvals:
        return PolicyDecision(action, "require-approval", tuple(approvals), "approval-required")
    allow = sorted(rule.rule_id for rule in matches if rule.effect == "allow")
    return PolicyDecision(action, "allow", tuple(allow), "explicit-allow")


@dataclass(frozen=True)
class InjectionFinding:
    finding_id: str
    category: str
    evidence_digest: str
    severity: str

    def __post_init__(self) -> None:
        require_id(self.finding_id, "finding_id")
        require_id(self.category, "category")
        require_digest(self.evidence_digest, "evidence_digest")
        if self.severity not in {"low", "medium", "high", "critical"}:
            raise SecurityPlaneError("invalid finding severity")


def inspect_untrusted_prompt(text: str) -> tuple[InjectionFinding, ...]:
    if not isinstance(text, str) or len(text) > MAX_TEXT_CHARS:
        raise SecurityPlaneError("invalid untrusted prompt")
    findings: list[InjectionFinding] = []
    for index, pattern in enumerate(_PROMPT_INJECTION_PATTERNS, start=1):
        for match_index, match in enumerate(pattern.finditer(text), start=1):
            snippet_digest = sha256(match.group(0).encode("utf-8")).hexdigest()
            findings.append(
                InjectionFinding(
                    f"PI-{index:02d}-{match_index:04d}",
                    "instruction-boundary-manipulation",
                    snippet_digest,
                    "high",
                )
            )
            if len(findings) > MAX_FINDINGS:
                raise SecurityPlaneError("prompt-injection finding budget exceeded")
    return tuple(findings)


@dataclass(frozen=True)
class SecretScanResult:
    redacted_text: str
    finding_digests: tuple[str, ...]

    @property
    def clean(self) -> bool:
        return not self.finding_digests


def isolate_secrets(text: str) -> SecretScanResult:
    if not isinstance(text, str) or len(text) > MAX_TEXT_CHARS:
        raise SecurityPlaneError("invalid secret-scan text")
    redacted = text
    findings: list[str] = []
    for pattern in _SECRET_PATTERNS:
        def replace(match: re.Match[str]) -> str:
            findings.append(sha256(match.group(0).encode("utf-8")).hexdigest())
            return "[REDACTED:secret]"
        redacted = pattern.sub(replace, redacted)
    return SecretScanResult(redacted, tuple(sorted(set(findings))))


@dataclass(frozen=True)
class DataClassification:
    classification: str
    labels: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.classification not in {"public", "internal", "confidential", "restricted"}:
            raise SecurityPlaneError("invalid data classification")
        labels = tuple(sorted(self.labels))
        if len(set(labels)) != len(labels) or len(labels) > MAX_LABELS:
            raise SecurityPlaneError("invalid data classification labels")
        for label in labels:
            require_id(label, "classification label")
        object.__setattr__(self, "labels", labels)


def classify_data(*, contains_secret: bool, contains_pii: bool, regulated: bool) -> DataClassification:
    for value in (contains_secret, contains_pii, regulated):
        if not isinstance(value, bool):
            raise SecurityPlaneError("classification inputs must be boolean")
    if contains_secret or regulated:
        return DataClassification("restricted", ("regulated" if regulated else "secret",))
    if contains_pii:
        return DataClassification("confidential", ("pii",))
    return DataClassification("internal", ())


@dataclass(frozen=True)
class PIIFinding:
    category: str
    evidence_digest: str

    def __post_init__(self) -> None:
        require_id(self.category, "PII category")
        require_digest(self.evidence_digest, "evidence_digest")


@dataclass(frozen=True)
class PIIHandlingResult:
    redacted_text: str
    findings: tuple[PIIFinding, ...]


def handle_pii(text: str) -> PIIHandlingResult:
    if not isinstance(text, str) or len(text) > MAX_TEXT_CHARS:
        raise SecurityPlaneError("invalid PII text")
    redacted = text
    findings: list[PIIFinding] = []
    for category, pattern in _PII_PATTERNS:
        def replace(match: re.Match[str], category: str = category) -> str:
            findings.append(PIIFinding(category, sha256(match.group(0).encode("utf-8")).hexdigest()))
            return f"[REDACTED:{category}]"
        redacted = pattern.sub(replace, redacted)
    return PIIHandlingResult(redacted, tuple(findings))


@dataclass(frozen=True)
class AuthorizationRequest:
    subject_id: str
    action: str
    resource_id: str
    granted_capabilities: tuple[str, ...]
    required_capabilities: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("subject_id", "action", "resource_id"):
            require_id(getattr(self, name), name)
        granted = tuple(sorted(self.granted_capabilities))
        required = tuple(sorted(self.required_capabilities))
        if len(set(granted)) != len(granted) or len(set(required)) != len(required):
            raise SecurityPlaneError("duplicate authorization capability")
        for cap in granted + required:
            require_id(cap, "capability")
        object.__setattr__(self, "granted_capabilities", granted)
        object.__setattr__(self, "required_capabilities", required)


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    reason: str
    request_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.allowed, bool):
            raise SecurityPlaneError("allowed must be boolean")
        require_id(self.reason, "reason")
        require_digest(self.request_digest, "request_digest")


def authorize(request: AuthorizationRequest) -> AuthorizationDecision:
    if not isinstance(request, AuthorizationRequest):
        raise SecurityPlaneError("AuthorizationRequest required")
    allowed = set(request.required_capabilities).issubset(request.granted_capabilities)
    return AuthorizationDecision(
        allowed,
        "authorized" if allowed else "capability-missing",
        digest_json(
            {
                "subject_id": request.subject_id,
                "action": request.action,
                "resource_id": request.resource_id,
                "granted_capabilities": list(request.granted_capabilities),
                "required_capabilities": list(request.required_capabilities),
            }
        ),
    )


@dataclass(frozen=True)
class ApprovalGate:
    gate_id: str
    action: str
    required_approvals: int
    approver_roles: tuple[str, ...]

    def __post_init__(self) -> None:
        require_id(self.gate_id, "gate_id")
        require_id(self.action, "action")
        if not _is_int(self.required_approvals) or not 1 <= self.required_approvals <= 100:
            raise SecurityPlaneError("invalid required_approvals")
        roles = tuple(sorted(self.approver_roles))
        if not roles or len(set(roles)) != len(roles):
            raise SecurityPlaneError("invalid approver_roles")
        for role in roles:
            require_id(role, "approver role")
        object.__setattr__(self, "approver_roles", roles)


def approval_satisfied(gate: ApprovalGate, approvals: Sequence[tuple[str, str]]) -> bool:
    unique_subjects: set[str] = set()
    valid = 0
    for subject, role in approvals:
        require_id(subject, "approver subject")
        require_id(role, "approver role")
        if subject in unique_subjects:
            raise SecurityPlaneError("duplicate approver subject")
        unique_subjects.add(subject)
        if role in gate.approver_roles:
            valid += 1
    return valid >= gate.required_approvals


@dataclass(frozen=True)
class SandboxBoundary:
    boundary_id: str
    writable_roots: tuple[str, ...]
    network_mode: str
    allow_process_spawn: bool

    def __post_init__(self) -> None:
        require_id(self.boundary_id, "boundary_id")
        roots = tuple(sorted(self.writable_roots))
        if len(set(roots)) != len(roots):
            raise SecurityPlaneError("duplicate writable root")
        for root in roots:
            if not isinstance(root, str) or not root.startswith("/") or ".." in root.split("/"):
                raise SecurityPlaneError("invalid writable root")
        object.__setattr__(self, "writable_roots", roots)
        if self.network_mode not in {"deny", "allowlisted-read", "allowlisted"}:
            raise SecurityPlaneError("invalid sandbox network mode")
        if not isinstance(self.allow_process_spawn, bool):
            raise SecurityPlaneError("allow_process_spawn must be boolean")

    def allows_path(self, path: str) -> bool:
        if not isinstance(path, str) or not path.startswith("/") or ".." in path.split("/"):
            raise SecurityPlaneError("invalid sandbox path")
        return any(path == root or path.startswith(root.rstrip("/") + "/") for root in self.writable_roots)


@dataclass(frozen=True)
class SupplyChainArtifact:
    artifact_id: str
    sha256: str
    source: str
    signer: str | None
    provenance_digest: str | None

    def __post_init__(self) -> None:
        require_id(self.artifact_id, "artifact_id")
        require_digest(self.sha256, "sha256")
        require_id(self.source, "source")
        if self.signer is not None:
            require_id(self.signer, "signer")
        if self.provenance_digest is not None:
            require_digest(self.provenance_digest, "provenance_digest")


def verify_supply_chain(
    artifact: SupplyChainArtifact,
    *,
    require_signature: bool = True,
    require_provenance: bool = True,
) -> bool:
    if not isinstance(artifact, SupplyChainArtifact):
        raise SecurityPlaneError("SupplyChainArtifact required")
    if require_signature and artifact.signer is None:
        return False
    if require_provenance and artifact.provenance_digest is None:
        return False
    return True


@dataclass(frozen=True)
class AuditEvent:
    sequence: int
    actor_id: str
    action: str
    object_digest: str
    outcome: str
    prior_event_digest: str | None = None

    def __post_init__(self) -> None:
        if not _is_int(self.sequence) or self.sequence < 0:
            raise SecurityPlaneError("invalid audit sequence")
        require_id(self.actor_id, "actor_id")
        require_id(self.action, "action")
        require_digest(self.object_digest, "object_digest")
        if self.outcome not in {"allowed", "denied", "failed", "completed"}:
            raise SecurityPlaneError("invalid audit outcome")
        if self.prior_event_digest is not None:
            require_digest(self.prior_event_digest, "prior_event_digest")
        if self.sequence == 0 and self.prior_event_digest is not None:
            raise SecurityPlaneError("genesis audit event cannot have parent")
        if self.sequence > 0 and self.prior_event_digest is None:
            raise SecurityPlaneError("non-genesis audit event requires parent")

    @property
    def digest(self) -> str:
        return digest_json(self.__dict__)


def append_audit_event(
    events: Sequence[AuditEvent],
    *,
    actor_id: str,
    action: str,
    object_digest: str,
    outcome: str,
) -> tuple[AuditEvent, ...]:
    for index, event in enumerate(events):
        if event.sequence != index:
            raise SecurityPlaneError("audit sequence drift")
        expected = events[index - 1].digest if index else None
        if event.prior_event_digest != expected:
            raise SecurityPlaneError("audit chain drift")
    prior = events[-1].digest if events else None
    event = AuditEvent(len(events), actor_id, action, object_digest, outcome, prior)
    return tuple(events) + (event,)


@dataclass(frozen=True)
class IncidentState:
    incident_id: str
    severity: str
    state: str
    blocked_capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_id(self.incident_id, "incident_id")
        if self.severity not in {"low", "medium", "high", "critical"}:
            raise SecurityPlaneError("invalid incident severity")
        if self.state not in {"open", "contained", "recovering", "closed"}:
            raise SecurityPlaneError("invalid incident state")
        caps = tuple(sorted(self.blocked_capabilities))
        if len(set(caps)) != len(caps):
            raise SecurityPlaneError("duplicate blocked capability")
        for cap in caps:
            require_id(cap, "blocked capability")
        object.__setattr__(self, "blocked_capabilities", caps)

    def allows(self, capability: str) -> bool:
        capability = require_id(capability, "capability")
        if self.state == "closed":
            return True
        if self.severity in {"high", "critical"}:
            return False
        return capability not in self.blocked_capabilities
