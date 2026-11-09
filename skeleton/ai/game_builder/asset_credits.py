"""Deterministic human-readable game attribution and third-party notice builder.

This emits usable credits and permission manifests for authored homebrew.
It does not decide whether a third-party license is lawful/compatible. Avoid
committing a third-party source package or pulling music, ROMs and artwork.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import unicodedata

from .legal_paths import MaterialKind, MaterialRecord


class CreditsError(ValueError):
    """Incomplete, inconsistent or unsafe authored-game rights notice."""


_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_UNSAFE_LICENSE_MARKERS = ("-NC", "-ND", "BY-NC", "BY-ND", "GPL-", "AGPL-", "-SA")


def _unsafe_invisible(value: str) -> bool:
    # Explicit bidirectional override, zero-width formatting and surrogate
    # characters can visually falsify legal authorship and licence obligations.
    return bool(_CONTROL.search(value)) or any(
        unicodedata.category(ch) in {"Cf", "Cs", "Zl", "Zp"}
        for ch in value
    )



@dataclass(frozen=True, slots=True)
class AttributionEntry:
    material_id: str
    original_author: str
    source_title: str
    rights_holder: str
    license_id: str
    license_url: str | None
    attribution_text: str
    license_text_sha256: str | None
    adaptation_description: str
    permitted_medium: str
    release_permission_evidence_sha256: str
    permission_externally_verified: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.material_id, str) or not _ID.fullmatch(self.material_id):
            raise CreditsError("invalid attribution identity")
        for label in (
            "original_author", "source_title", "rights_holder", "license_id",
            "adaptation_description", "permitted_medium", "attribution_text",
        ):
            value = getattr(self, label)
            if not isinstance(value, str) or not 1 <= len(value) <= 500 or _unsafe_invisible(value):
                raise CreditsError("missing/unsafe credit line " + label)
        if self.license_url is not None and (
            not isinstance(self.license_url, str) or len(self.license_url) > 512
            or not self.license_url.startswith("https://") or _unsafe_invisible(self.license_url)
        ):
            raise CreditsError("untrusted license URL")
        for name in ("license_text_sha256", "release_permission_evidence_sha256"):
            value = getattr(self, name)
            if value is None and name == "license_text_sha256":
                continue
            if not isinstance(value, str) or not _SHA.fullmatch(value):
                raise CreditsError("license and permission evidence must be a SHA-256")
        if type(self.permission_externally_verified) is not bool:
            raise CreditsError("external evidence statement must be boolean")


@dataclass(frozen=True, slots=True)
class CreditsBundle:
    project_id: str
    target_platform_id: str
    credits_md: str
    third_party_notices_txt: str
    inventory_json: str
    bundle_sha256: str
    review_issues: tuple[str, ...]
    release_authorized: bool = False
    licensed_material_independently_cleared: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.project_id, str) or not _ID.fullmatch(self.project_id):
            raise CreditsError("invalid credited project")
        if not isinstance(self.target_platform_id, str) or not _ID.fullmatch(self.target_platform_id):
            raise CreditsError("invalid credited platform")
        if any(type(getattr(self, v)) is not bool or getattr(self, v) is not False for v in (
            "release_authorized", "licensed_material_independently_cleared",
        )):
            raise CreditsError("credits cannot grant a release permission or legal clearance")
        if not isinstance(self.review_issues, tuple) or any(
            not isinstance(v, str) or not v for v in self.review_issues
        ):
            raise CreditsError("invalid material review issues")
        if any(not isinstance(v, str) for v in (
            self.credits_md, self.third_party_notices_txt, self.inventory_json
        )):
            raise CreditsError("invalid authored notices")
        expected = sha256((
            self.credits_md + "\0" + self.third_party_notices_txt + "\0" + self.inventory_json
        ).encode("utf-8")).hexdigest()
        if not _is_sha256(self.bundle_sha256) or expected != self.bundle_sha256:
            raise CreditsError("reviewed credit and notice bytes do not match digest")
        try:
            inventory = json.loads(self.inventory_json)
        except (TypeError, ValueError) as exc:
            raise CreditsError("invalid rights inventory") from exc
        if (not isinstance(inventory, dict) or
            inventory.get("project_id") != self.project_id or
            inventory.get("target_platform_id") != self.target_platform_id or
            inventory.get("legal_clearance_granted") is not False or
            inventory.get("review_issues") != list(self.review_issues)):
            raise CreditsError("credit inventory metadata differs from signed manifest")

    def as_receipt(self) -> dict[str, object]:
        return {
            "schema": "skeleton.game_builder.credits_bundle.v1",
            "project_id": self.project_id,
            "target_platform_id": self.target_platform_id,
            "bundle_sha256": self.bundle_sha256,
            "review_issues": list(self.review_issues),
            "release_authorized": False,
            "third_party_licenses_legally_certified": False,
        }


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and bool(_SHA.fullmatch(value))


def _md(text: str) -> str:
    """Escape untrusted credit strings before treating them as Markdown."""
    return "".join("\\" + c if c in "\\<>[]()*_`~!|#" else c for c in text)


def compile_game_credits(
    project_id: str, target_platform_id: str, *,
    materials: tuple[MaterialRecord, ...],
    third_party: tuple[AttributionEntry, ...],
    original_authors: tuple[str, ...],
) -> CreditsBundle:
    """Check 1:1 third-party chain and generate legally reviewable actual notices."""
    if not isinstance(project_id, str) or not _ID.fullmatch(project_id):
        raise CreditsError("invalid game project")
    if not isinstance(target_platform_id, str) or not _ID.fullmatch(target_platform_id):
        raise CreditsError("invalid destination")
    if not isinstance(materials, tuple) or not materials or any(
        not isinstance(m, MaterialRecord) for m in materials
    ):
        raise CreditsError("typed all-game material inventory required")
    if not isinstance(third_party, tuple) or any(
        not isinstance(e, AttributionEntry) for e in third_party
    ):
        raise CreditsError("typed third-party credits required")
    if not isinstance(original_authors, tuple) or not original_authors or any(
        not isinstance(v, str) or not 1 <= len(v) <= 200 or _unsafe_invisible(v)
        for v in original_authors
    ):
        raise CreditsError("named original authorship required")
    if len(set(original_authors)) != len(original_authors):
        raise CreditsError("duplicate original authors")
    if len(materials) > 1000 or len(third_party) > 1000:
        raise CreditsError("bounded attribution batch exceeded")
    by_id = {m.material_id:m for m in materials}
    by_entry = {e.material_id:e for e in third_party}
    if len(by_id) != len(materials) or len(by_entry) != len(third_party):
        raise CreditsError("duplicate material/credit identities")
    if any(m.kind is MaterialKind.UNLICENSED_THIRD_PARTY for m in materials):
        raise CreditsError("known unlicensed protected content cannot enter a credits bundle")
    if any(m.kind is MaterialKind.UNKNOWN for m in materials):
        raise CreditsError("unknown asset origin must be held before credits generation")
    licensed = {
        m.material_id for m in materials if m.kind is MaterialKind.LICENSED_THIRD_PARTY
    }
    if set(by_entry) != licensed:
        raise CreditsError("every included third-party asset must have exactly one attribution entry")
    concerns: set[str] = set()
    rows: list[dict[str, object]] = []
    for material in sorted(materials, key=lambda m:m.material_id):
        entry = by_entry.get(material.material_id)
        if entry:
            if not material.evidence_sha256 or (
                material.license_identifier != entry.license_id
            ) or (not material.permission_satisfies_proposed_use):
                concerns.add("RIGHTS_OR_LICENSE_SCOPE_UNVERIFIED:" + material.material_id)
            if material.attribution_required and (
                not material.attribution_recorded or not entry.attribution_text
            ):
                concerns.add("ATTRIBUTION_OBLIGATIONS_UNVERIFIED:" + material.material_id)
            if not entry.permission_externally_verified:
                concerns.add("PERMISSION_EVIDENCE_NEEDS_INDEPENDENT_REVIEW:" + material.material_id)
            if any(term in entry.license_id.upper() for term in _UNSAFE_LICENSE_MARKERS):
                concerns.add("SHAREALIKE_COPYLEFT_OR_NONCOMMERCIAL_SCOPE_REVIEW:" + material.material_id)
            if entry.license_text_sha256 is None:
                concerns.add("LICENSE_TEXT_NOT_BOUND_TO_NOTICE:" + material.material_id)
        rows.append({
            "material_id":material.material_id,
            "category":material.category,
            "rights_basis":material.kind.value,
            "source_evidence_sha256":material.evidence_sha256,
            "license_id":entry.license_id if entry else material.license_identifier,
            "credited_author":entry.original_author if entry else None,
            "credited_rightsholder":entry.rights_holder if entry else None,
            "attribution_text":entry.attribution_text if entry else None,
            "permitted_medium":entry.permitted_medium if entry else None,
            "external_permission_checked":entry.permission_externally_verified if entry else None,
            "license_text_sha256":entry.license_text_sha256 if entry else None,
        })
    if not concerns and licensed:
        concerns.add("FINAL_HUMAN_LICENSE_AND_DISTRIBUTION_REVIEW_REQUIRED")
    # A credits file cannot establish truth, and merely naming a publisher does
    # not authorize an otherwise forbidden copyrighted game adaptation.
    title = "# Original game credits\n\n"
    author_lines = "".join("- " + _md(a) + "\n" for a in original_authors)
    credits = title + "## Independently authored work\n" + author_lines
    if third_party:
        credits += "\n## Third-party components — permission review required\n"
        for entry in sorted(third_party, key=lambda e:e.material_id):
            credits += "- " + _md(entry.source_title) + " — " + _md(entry.attribution_text) + "\n"
    credits += "\nThis document records author declarations, not publisher release authorization.\n"
    notices = ("THIRD-PARTY MATERIAL NOTICES\n"
               "Credit and notice text does not alone grant permission to redistribute game assets.\n\n")
    for entry in sorted(third_party, key=lambda e:e.material_id):
        notices += (
            "Asset: " + entry.material_id + "\n"
            "Work: " + entry.source_title + "\n"
            "Creator: " + entry.original_author + "\n"
            "Rights holder: " + entry.rights_holder + "\n"
            "License: " + entry.license_id + "\n"
            "License reference: " + (entry.license_url or "NOT RECORDED") + "\n"
            "License-text SHA256: " + (entry.license_text_sha256 or "NOT RECORDED") + "\n"
            "Adaptation disclosure: " + entry.adaptation_description + "\n"
            "Proposed target/medium: " + entry.permitted_medium + "\n"
            "Attribution: " + entry.attribution_text + "\n\n"
        )
    inventory = json.dumps({
        "schema":"skeleton.game_builder.attribution.v1",
        "project_id":project_id, "target_platform_id":target_platform_id,
        "original_authors":list(original_authors), "third_party_records":rows,
        "review_issues":sorted(concerns),
        "legal_clearance_granted":False,
    }, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    content_digest = sha256((
        credits + "\0" + notices + "\0" + inventory
    ).encode("utf-8")).hexdigest()
    return CreditsBundle(
        project_id, target_platform_id, credits, notices, inventory,
        content_digest, tuple(sorted(concerns)),
    )


def export_game_credits(bundle: CreditsBundle, destination: str | Path, *, authorized: bool) -> Path:
    """Create a new credits directory, never overwrite existing rights notices."""
    if type(authorized) is not bool or not authorized:
        raise PermissionError("game credits require explicit export authorization")
    if not isinstance(bundle, CreditsBundle):
        raise CreditsError("typed game credit bundle required")
    path = Path(destination)
    if path.exists() or path.is_symlink():
        raise FileExistsError("cannot replace existing credits")
    path.mkdir(parents=False)
    (path / "CREDITS.md").write_text(bundle.credits_md, encoding="utf-8")
    (path / "THIRD_PARTY_NOTICES.txt").write_text(bundle.third_party_notices_txt, encoding="utf-8")
    (path / "material_inventory.json").write_text(bundle.inventory_json, encoding="utf-8")
    return path
