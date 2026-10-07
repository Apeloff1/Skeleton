"""Evidence-bound trust and experience contracts for P3.

Explainability, accessibility, internationalization and compliance are treated
as runtime contracts rather than presentation claims.  Explanations cite exact
operation/evidence identities; accessibility acceptance requires semantic,
non-visual control paths; locale policy keeps machine parsing canonical and
separate from presentation; compliance controls are scoped, owned,
time-bounded and evidence-backed instead of being inferred from a label.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import re
from typing import Mapping, Sequence


class TrustExperienceError(RuntimeError):
    """A trust/experience artifact cannot satisfy its evidence contract."""


def _text(name: str, value: object, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TrustExperienceError(f"{name} must be non-empty text")
    result = value.strip()
    if len(result) > maximum:
        raise TrustExperienceError(f"{name} exceeds {maximum} characters")
    return result


def _unique(name: str, values: Sequence[str], *, minimum: int = 0) -> tuple[str, ...]:
    result: list[str] = []
    for raw in values:
        item = _text(name, raw)
        if item in result:
            raise TrustExperienceError(f"{name} contains duplicate {item}")
        result.append(item)
    if len(result) < minimum:
        raise TrustExperienceError(f"{name} requires at least {minimum} entries")
    return tuple(result)


def _instant(name: str, value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise TrustExperienceError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise TrustExperienceError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
            default=lambda item: item.isoformat() if isinstance(item, datetime) else str(item),
        )
    except (TypeError, ValueError) as exc:
        raise TrustExperienceError("trust artifact is not deterministic JSON") from exc
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ExplanationClaim:
    claim_id: str
    statement: str
    operation_ref: str
    evidence_refs: tuple[str, ...]
    confidence_label: str = "bounded"

    def __post_init__(self) -> None:
        object.__setattr__(self, "claim_id", _text("claim_id", self.claim_id, 256))
        object.__setattr__(self, "statement", _text("statement", self.statement))
        object.__setattr__(
            self, "operation_ref", _text("operation_ref", self.operation_ref, 512)
        )
        object.__setattr__(
            self, "evidence_refs", _unique("evidence_ref", self.evidence_refs, minimum=1)
        )
        if self.confidence_label not in {"bounded", "uncertain", "verified"}:
            raise TrustExperienceError("unsupported explanation confidence label")


@dataclass(frozen=True, slots=True)
class ExplanationBundle:
    explanation_id: str
    operation_ref: str
    claims: tuple[ExplanationClaim, ...]
    provenance_refs: tuple[str, ...]
    caveats: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "explanation_id", _text("explanation_id", self.explanation_id, 256)
        )
        object.__setattr__(
            self, "operation_ref", _text("operation_ref", self.operation_ref, 512)
        )
        if not self.claims:
            raise TrustExperienceError("explanation requires at least one claim")
        ids: set[str] = set()
        for claim in self.claims:
            if not isinstance(claim, ExplanationClaim):
                raise TrustExperienceError("claims must be ExplanationClaim")
            if claim.claim_id in ids:
                raise TrustExperienceError("duplicate explanation claim id")
            ids.add(claim.claim_id)
            if claim.operation_ref != self.operation_ref:
                raise TrustExperienceError("explanation claim operation provenance drift")
        object.__setattr__(
            self,
            "provenance_refs",
            _unique("provenance_ref", self.provenance_refs, minimum=1),
        )
        object.__setattr__(
            self, "caveats", _unique("caveat", self.caveats)
        )

    @property
    def evidence_refs(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(ref for claim in self.claims for ref in claim.evidence_refs)
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "explanation_id": self.explanation_id,
                "operation_ref": self.operation_ref,
                "claims": [
                    {
                        "claim_id": claim.claim_id,
                        "statement": claim.statement,
                        "evidence_refs": list(claim.evidence_refs),
                        "confidence_label": claim.confidence_label,
                    }
                    for claim in self.claims
                ],
                "provenance_refs": list(self.provenance_refs),
                "caveats": list(self.caveats),
            }
        )


class InteractionKind(str, Enum):
    ACTION = "action"
    STATUS = "status"
    APPROVAL = "approval"
    CANCELLATION = "cancellation"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class AccessibilitySurface:
    surface_id: str
    kind: InteractionKind
    semantic_name: str
    keyboard_reachable: bool
    screen_reader_exposed: bool
    visual_only: bool = False
    motion_required: bool = False
    text_equivalent: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "surface_id", _text("surface_id", self.surface_id, 256))
        if not isinstance(self.kind, InteractionKind):
            object.__setattr__(self, "kind", InteractionKind(str(self.kind)))
        object.__setattr__(
            self, "semantic_name", _text("semantic_name", self.semantic_name, 512)
        )
        if self.text_equivalent is not None:
            object.__setattr__(
                self, "text_equivalent", _text("text_equivalent", self.text_equivalent, 2048)
            )


@dataclass(frozen=True, slots=True)
class AccessibilityReceipt:
    surface_ids: tuple[str, ...]
    required_kinds: tuple[str, ...]
    semantic_complete: bool
    keyboard_complete: bool
    non_visual_complete: bool

    @property
    def passed(self) -> bool:
        return (
            self.semantic_complete
            and self.keyboard_complete
            and self.non_visual_complete
        )


class AccessibilityValidator:
    """Fail closed for critical semantic, cancellation and approval surfaces."""

    REQUIRED = (
        InteractionKind.ACTION,
        InteractionKind.STATUS,
        InteractionKind.APPROVAL,
        InteractionKind.CANCELLATION,
        InteractionKind.ERROR,
    )

    def validate(self, surfaces: Sequence[AccessibilitySurface]) -> AccessibilityReceipt:
        if not surfaces:
            raise TrustExperienceError("accessibility surface inventory is empty")
        by_kind: dict[InteractionKind, list[AccessibilitySurface]] = {}
        ids: list[str] = []
        for surface in surfaces:
            if not isinstance(surface, AccessibilitySurface):
                raise TrustExperienceError("invalid accessibility surface")
            if surface.surface_id in ids:
                raise TrustExperienceError("duplicate accessibility surface id")
            ids.append(surface.surface_id)
            by_kind.setdefault(surface.kind, []).append(surface)

        missing = [kind.value for kind in self.REQUIRED if kind not in by_kind]
        if missing:
            raise TrustExperienceError(
                "critical accessibility kinds missing: " + ",".join(missing)
            )
        semantic = all(surface.semantic_name for surface in surfaces)
        keyboard = all(
            any(surface.keyboard_reachable for surface in by_kind[kind])
            for kind in (InteractionKind.ACTION, InteractionKind.APPROVAL, InteractionKind.CANCELLATION)
        )
        non_visual = all(
            not surface.visual_only
            and surface.screen_reader_exposed
            and (surface.text_equivalent is not None or bool(surface.semantic_name))
            for surface in surfaces
        )
        receipt = AccessibilityReceipt(
            surface_ids=tuple(ids),
            required_kinds=tuple(kind.value for kind in self.REQUIRED),
            semantic_complete=semantic,
            keyboard_complete=keyboard,
            non_visual_complete=non_visual,
        )
        if not receipt.passed:
            raise TrustExperienceError("critical accessibility acceptance failed")
        return receipt


_LOCALE_RE = re.compile(r"^[a-z]{2,3}(?:-[A-Z]{2})?$")
_CANONICAL_MACHINE_NUMBER = re.compile(r"^-?(?:0|[1-9]\d*)(?:\.\d+)?$")


@dataclass(frozen=True, slots=True)
class LocalePolicy:
    default_locale: str = "en-US"
    supported_locales: tuple[str, ...] = ("en-US",)
    fallback_locale: str = "en-US"

    def __post_init__(self) -> None:
        supported = _unique("supported_locale", self.supported_locales, minimum=1)
        for locale in supported:
            if _LOCALE_RE.fullmatch(locale) is None:
                raise TrustExperienceError(f"invalid canonical locale: {locale}")
        default = _text("default_locale", self.default_locale, 16)
        fallback = _text("fallback_locale", self.fallback_locale, 16)
        if default not in supported or fallback not in supported:
            raise TrustExperienceError("default/fallback locale must be supported")
        object.__setattr__(self, "supported_locales", supported)

    def resolve(self, requested: str | None) -> str:
        if requested is None or not requested.strip():
            return self.default_locale
        raw = requested.strip().replace("_", "-")
        parts = raw.split("-")
        normalized = parts[0].lower()
        if len(parts) == 2:
            normalized += "-" + parts[1].upper()
        if normalized in self.supported_locales:
            return normalized
        return self.fallback_locale

    @staticmethod
    def parse_machine_number(value: str) -> float:
        text = _text("machine_number", value, 128)
        if _CANONICAL_MACHINE_NUMBER.fullmatch(text) is None:
            raise TrustExperienceError(
                "machine numbers must use locale-independent canonical decimal syntax"
            )
        return float(text)


@dataclass(frozen=True, slots=True)
class ComplianceControl:
    control_id: str
    control_family: str
    applicability: tuple[str, ...]
    owner_id: str
    evidence_refs: tuple[str, ...]
    valid_from: datetime
    valid_until: datetime | None = None
    source_refs: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "control_id", _text("control_id", self.control_id, 256))
        object.__setattr__(
            self, "control_family", _text("control_family", self.control_family, 256)
        )
        object.__setattr__(
            self, "applicability", _unique("applicability", self.applicability, minimum=1)
        )
        object.__setattr__(self, "owner_id", _text("owner_id", self.owner_id, 256))
        object.__setattr__(
            self, "evidence_refs", _unique("evidence_ref", self.evidence_refs, minimum=1)
        )
        object.__setattr__(
            self, "source_refs", _unique("source_ref", self.source_refs, minimum=1)
        )
        start = _instant("valid_from", self.valid_from)
        object.__setattr__(self, "valid_from", start)
        if self.valid_until is not None:
            end = _instant("valid_until", self.valid_until)
            if end <= start:
                raise TrustExperienceError("valid_until must be after valid_from")
            object.__setattr__(self, "valid_until", end)
        object.__setattr__(self, "notes", self.notes.strip())

    def active_at(self, instant: datetime) -> bool:
        now = _instant("instant", instant)
        if now < self.valid_from:
            return False
        return self.valid_until is None or now < self.valid_until


@dataclass(frozen=True, slots=True)
class ComplianceDecision:
    scope: str
    control_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    owner_ids: tuple[str, ...]
    evaluated_at: datetime
    complete: bool


class ComplianceRegistry:
    """Evidence registry only; it does not infer legal applicability by itself."""

    def __init__(self) -> None:
        self._controls: dict[str, ComplianceControl] = {}

    def register(self, control: ComplianceControl) -> ComplianceControl:
        if not isinstance(control, ComplianceControl):
            raise TypeError("control must be ComplianceControl")
        prior = self._controls.get(control.control_id)
        if prior is not None and prior != control:
            raise TrustExperienceError("compliance control identity conflict")
        self._controls[control.control_id] = control
        return control

    def evaluate(
        self,
        *,
        scope: str,
        required_control_ids: Sequence[str],
        at: datetime,
    ) -> ComplianceDecision:
        normalized_scope = _text("scope", scope, 512)
        required = _unique("required_control_id", required_control_ids, minimum=1)
        now = _instant("at", at)
        controls: list[ComplianceControl] = []
        for control_id in required:
            control = self._controls.get(control_id)
            if control is None:
                raise TrustExperienceError(f"required compliance control missing: {control_id}")
            if normalized_scope not in control.applicability:
                raise TrustExperienceError(
                    f"control {control_id} does not declare scope {normalized_scope}"
                )
            if not control.active_at(now):
                raise TrustExperienceError(f"control {control_id} is not current")
            controls.append(control)
        return ComplianceDecision(
            scope=normalized_scope,
            control_ids=tuple(control.control_id for control in controls),
            evidence_refs=tuple(
                dict.fromkeys(ref for control in controls for ref in control.evidence_refs)
            ),
            owner_ids=tuple(dict.fromkeys(control.owner_id for control in controls)),
            evaluated_at=now,
            complete=len(controls) == len(required),
        )


__all__ = [
    "AccessibilityReceipt",
    "AccessibilitySurface",
    "AccessibilityValidator",
    "ComplianceControl",
    "ComplianceDecision",
    "ComplianceRegistry",
    "ExplanationBundle",
    "ExplanationClaim",
    "InteractionKind",
    "LocalePolicy",
    "TrustExperienceError",
]
