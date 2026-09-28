"""P1 release attribution and notice qualification.

The release notice is derived from exact-head license bytes. Registry metadata
selects which license files/components are shipped; the qualifier requires that
registry coverage exactly matches discovered release license paths and binds the
manifest to the accepted REL-01 release candidate.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

from skeleton.contracts.canonical import EvidenceRef
from skeleton.release.qualification import ReleaseQualificationDecision


RELEASE_ATTRIBUTION_SCHEMA_VERSION = 1
RELEASE_ATTRIBUTION_TASK_ID = "P1-REL-06"
RELEASE_ATTRIBUTION_ACCOUNTABILITY_ID = "ACC-P1-REL-06"
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,511}$")


class ReleaseAttributionError(ValueError):
    """Release attribution evidence is malformed or incomplete."""


def _token(value: object, field: str, *, maximum: int = 512) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or not _TOKEN_RE.fullmatch(value)
    ):
        raise ReleaseAttributionError(
            f"{field} must be a canonical token"
        )
    return value


def _sha40(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA40_RE.fullmatch(value):
        raise ReleaseAttributionError(
            f"{field} must be lowercase 40-character git SHA"
        )
    return value


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ReleaseAttributionError(
            f"{field} must be lowercase sha256"
        )
    return value


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ReleaseAttributionError(
            "attribution payload must be canonical JSON"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


@dataclass(frozen=True, slots=True)
class AttributionEntry:
    component_id: str
    source_ref: str
    license_path: str
    license_digest: str
    third_party: bool

    def __post_init__(self) -> None:
        for field in ("component_id", "source_ref", "license_path"):
            object.__setattr__(
                self,
                field,
                _token(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "license_digest",
            _sha256(self.license_digest, "license_digest"),
        )
        if not isinstance(self.third_party, bool):
            raise ReleaseAttributionError(
                "third_party must be boolean"
            )
        if self.third_party and self.license_path == "LICENSE":
            raise ReleaseAttributionError(
                "root project license cannot be third-party"
            )
        if not self.third_party and self.license_path != "LICENSE":
            raise ReleaseAttributionError(
                "first-party release license must be root LICENSE"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "source_ref": self.source_ref,
            "license_path": self.license_path,
            "license_digest": self.license_digest,
            "third_party": self.third_party,
        }


def render_release_notice(entries: Iterable[AttributionEntry]) -> str:
    rows = tuple(entries)
    if not rows:
        raise ReleaseAttributionError(
            "release notice requires attribution entries"
        )
    ordered = tuple(
        sorted(
            rows,
            key=lambda item: (
                item.third_party,
                item.component_id,
                item.license_path,
            ),
        )
    )
    lines = [
        "Skeleton Release Attribution Notice",
        "===================================",
        "",
        "This notice is generated from exact-head license files.",
        "",
    ]
    for entry in ordered:
        scope = "third-party" if entry.third_party else "first-party"
        lines.extend(
            [
                f"Component: {entry.component_id}",
                f"Scope: {scope}",
                f"Source: {entry.source_ref}",
                f"License file: {entry.license_path}",
                f"License SHA-256: {entry.license_digest}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


@dataclass(frozen=True, slots=True)
class ReleaseAttributionManifest:
    source_commit: str
    release_qualification_digest: str
    entries: tuple[AttributionEntry, ...]
    notice_digest: str
    schema_version: int = RELEASE_ATTRIBUTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_commit",
            _sha40(self.source_commit, "source_commit"),
        )
        object.__setattr__(
            self,
            "release_qualification_digest",
            _sha256(
                self.release_qualification_digest,
                "release_qualification_digest",
            ),
        )
        if not isinstance(self.entries, tuple) or not self.entries:
            raise ReleaseAttributionError(
                "entries must be a non-empty tuple"
            )
        if any(
            not isinstance(item, AttributionEntry)
            for item in self.entries
        ):
            raise ReleaseAttributionError(
                "entries must contain AttributionEntry"
            )
        component_ids = [item.component_id for item in self.entries]
        license_paths = [item.license_path for item in self.entries]
        if len(component_ids) != len(set(component_ids)):
            raise ReleaseAttributionError(
                "component IDs must be unique"
            )
        if len(license_paths) != len(set(license_paths)):
            raise ReleaseAttributionError(
                "license paths must be unique"
            )
        if sum(not item.third_party for item in self.entries) != 1:
            raise ReleaseAttributionError(
                "manifest requires exactly one first-party root license"
            )
        expected = hashlib.sha256(
            render_release_notice(self.entries).encode("utf-8")
        ).hexdigest()
        object.__setattr__(
            self,
            "notice_digest",
            _sha256(self.notice_digest, "notice_digest"),
        )
        if self.notice_digest != expected:
            raise ReleaseAttributionError(
                "notice digest does not match deterministic notice"
            )
        if self.schema_version != RELEASE_ATTRIBUTION_SCHEMA_VERSION:
            raise ReleaseAttributionError(
                "unsupported attribution manifest schema"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": RELEASE_ATTRIBUTION_TASK_ID,
            "accountability_id": RELEASE_ATTRIBUTION_ACCOUNTABILITY_ID,
            "source_commit": self.source_commit,
            "release_qualification_digest": (
                self.release_qualification_digest
            ),
            "entries": [
                item.payload()
                for item in sorted(
                    self.entries,
                    key=lambda row: row.license_path,
                )
            ],
            "notice_digest": self.notice_digest,
        }

    @property
    def manifest_digest(self) -> str:
        return _digest(self.payload())


@dataclass(frozen=True, slots=True)
class ReleaseAttributionDecision:
    accepted: bool
    reasons: tuple[str, ...]
    source_commit: str
    release_qualification_digest: str
    manifest_digest: str
    notice_digest: str
    entry_count: int
    task_id: str = RELEASE_ATTRIBUTION_TASK_ID
    accountability_id: str = RELEASE_ATTRIBUTION_ACCOUNTABILITY_ID
    schema_version: int = RELEASE_ATTRIBUTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise ReleaseAttributionError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item
            for item in self.reasons
        ):
            raise ReleaseAttributionError(
                "reasons must contain non-empty strings"
            )
        object.__setattr__(
            self,
            "source_commit",
            _sha40(self.source_commit, "source_commit"),
        )
        for field in (
            "release_qualification_digest",
            "manifest_digest",
            "notice_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        if (
            isinstance(self.entry_count, bool)
            or not isinstance(self.entry_count, int)
            or self.entry_count < 1
        ):
            raise ReleaseAttributionError(
                "entry_count must be positive integer"
            )
        if self.task_id != RELEASE_ATTRIBUTION_TASK_ID:
            raise ReleaseAttributionError("task_id drift")
        if self.accountability_id != RELEASE_ATTRIBUTION_ACCOUNTABILITY_ID:
            raise ReleaseAttributionError("accountability_id drift")
        if self.schema_version != RELEASE_ATTRIBUTION_SCHEMA_VERSION:
            raise ReleaseAttributionError(
                "unsupported attribution decision schema"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "source_commit": self.source_commit,
            "release_qualification_digest": (
                self.release_qualification_digest
            ),
            "manifest_digest": self.manifest_digest,
            "notice_digest": self.notice_digest,
            "entry_count": self.entry_count,
            "production_authority": False,
        }

    @property
    def decision_digest(self) -> str:
        return _digest(self.payload())

    def accepted_evidence_ref(self) -> EvidenceRef:
        if not self.accepted:
            raise ReleaseAttributionError(
                "rejected attribution cannot become promotion evidence"
            )
        return EvidenceRef(
            source=f"p1:rel-06:attribution:{self.source_commit}",
            digest=self.decision_digest,
            category="release_attribution_qualification",
        )


def qualify_release_attribution(
    *,
    release_qualification: ReleaseQualificationDecision,
    manifest: ReleaseAttributionManifest,
    observed_license_digests: Mapping[str, str],
    discovered_license_paths: Iterable[str],
) -> ReleaseAttributionDecision:
    if not isinstance(
        release_qualification,
        ReleaseQualificationDecision,
    ):
        raise TypeError(
            "release_qualification must be ReleaseQualificationDecision"
        )
    if not isinstance(manifest, ReleaseAttributionManifest):
        raise TypeError("manifest must be ReleaseAttributionManifest")
    if not isinstance(observed_license_digests, Mapping):
        raise TypeError(
            "observed_license_digests must be a mapping"
        )

    reasons: list[str] = []
    if not release_qualification.accepted:
        reasons.append("release-qualification-rejected")
    if manifest.source_commit != release_qualification.source_commit:
        reasons.append("attribution-source-commit-mismatch")
    if (
        manifest.release_qualification_digest
        != release_qualification.decision_digest
    ):
        reasons.append("attribution-release-digest-mismatch")

    registered = {item.license_path for item in manifest.entries}
    discovered = {
        _token(path, "discovered_license_paths")
        for path in discovered_license_paths
    }
    if registered != discovered:
        for path in sorted(discovered - registered):
            reasons.append(f"license-unattributed:{path}")
        for path in sorted(registered - discovered):
            reasons.append(f"license-registry-stale:{path}")

    for entry in manifest.entries:
        observed = observed_license_digests.get(entry.license_path)
        if observed is None:
            reasons.append(
                f"license-digest-missing:{entry.license_path}"
            )
            continue
        try:
            digest = _sha256(
                observed,
                f"observed_license_digests[{entry.license_path}]",
            )
        except ReleaseAttributionError:
            reasons.append(
                f"license-digest-invalid:{entry.license_path}"
            )
            continue
        if digest != entry.license_digest:
            reasons.append(
                f"license-digest-mismatch:{entry.license_path}"
            )

    expected_notice_digest = hashlib.sha256(
        render_release_notice(manifest.entries).encode("utf-8")
    ).hexdigest()
    if manifest.notice_digest != expected_notice_digest:
        reasons.append("notice-digest-mismatch")

    normalized = tuple(sorted(set(reasons)))
    return ReleaseAttributionDecision(
        accepted=not normalized,
        reasons=normalized,
        source_commit=release_qualification.source_commit,
        release_qualification_digest=release_qualification.decision_digest,
        manifest_digest=manifest.manifest_digest,
        notice_digest=manifest.notice_digest,
        entry_count=len(manifest.entries),
    )


__all__ = [
    "RELEASE_ATTRIBUTION_ACCOUNTABILITY_ID",
    "RELEASE_ATTRIBUTION_SCHEMA_VERSION",
    "RELEASE_ATTRIBUTION_TASK_ID",
    "AttributionEntry",
    "ReleaseAttributionDecision",
    "ReleaseAttributionError",
    "ReleaseAttributionManifest",
    "qualify_release_attribution",
    "render_release_notice",
]
