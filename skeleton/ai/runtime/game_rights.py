"""Rights-aware authoring and modification admission for cross-era games.

This gate checks *explicit evidence and claims*; it is not a legal
opinion, ownership oracle, legal exemption or permission to circumvent
technological measures. No game/ROM/firmware/BIOS/SDK bytes are loaded.
User assertions are UNVERIFIED and final distribution requires separate
rights-holder/qualified human review.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

SCHEMA = "skeleton.game.rights.v1"
MAX_ASSETS = 128
MAX_TITLE = 100
_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_JURISDICTIONS = {"NO", "EEA", "EU", "US", "GB", "CA", "JP", "AU", "OTHER"}
_USE = frozenset({"modify", "embed", "distribute", "commercial", "train"})
_SOURCE = {
    "original": "original_author_attested",
    "commissioned": "contractual_rights_review_needed",
    "open_licensed": "license_terms_review_needed",
    "licensed": "license_scope_review_needed",
    "public_domain_claimed": "jurisdiction_status_review_needed",
    "interoperability_research": "limited_interoperability_review_needed",
    "user_supplied_unverified": "rights_not_established",
}
_BLOCKED_KINDS = {
    "pirated_rom", "unknown", "leaked_sdk", "extracted_firmware",
    "unlicensed_commercial_asset", "circumvention_output",
}
_ACTIONS = {
    "original_game", "independent_mechanics", "modify_authorized",
    "interoperability_study", "private_reproduction",
    "publish", "train_on_assets",
}


class GameRightsError(ValueError):
    """Rights evidence missing, inconsistent or unsafe for requested use."""


def _sha(value: Any) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise GameRightsError("content hashes must be lowercase SHA-256")
    return value


def _id(value: Any) -> str:
    if not isinstance(value, str) or _NAME.fullmatch(value) is None:
        raise GameRightsError("asset IDs must be unique bounded ASCII slugs")
    return value


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("ascii")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise GameRightsError("rights receipt is not canonical JSON") from exc


def _source(item: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(item, dict) or set(item) != {
        "asset_id", "sha256", "source_kind", "licensor",
        "license_reference", "allowed_uses", "contains_third_party_content",
        "contains_trademarks", "contains_technological_protection",
    }:
        raise GameRightsError("asset provenance must have exactly the required fields")
    name = _id(item["asset_id"])
    digest = _sha(item["sha256"])
    kind = item["source_kind"]
    if kind in _BLOCKED_KINDS:
        raise GameRightsError("asset category is inadmissible")
    if kind not in _SOURCE:
        raise GameRightsError("unknown or undeclared source provenance")
    licensor, proof = item["licensor"], item["license_reference"]
    if (
        not isinstance(licensor, str) or not 1 <= len(licensor) <= 128
        or not isinstance(proof, str) or not 1 <= len(proof) <= 256
        or "\x00" in licensor or "\x00" in proof
        or any(type(item[k]) is not bool for k in (
            "contains_third_party_content", "contains_trademarks",
            "contains_technological_protection"
        ))
    ):
        raise GameRightsError("rights chain details are invalid")
    permissions = item["allowed_uses"]
    if (
        not isinstance(permissions, list)
        or not permissions or len(permissions) != len(set(str(x) for x in permissions))
        or any(not isinstance(x, str) or x not in _USE for x in permissions)
    ):
        raise GameRightsError("asset permission scope is invalid")
    if item["contains_technological_protection"]:
        raise GameRightsError(
            "protected/circumvention-dependent content cannot enter this authoring path"
        )
    if kind == "original" and item["contains_third_party_content"]:
        raise GameRightsError(
            "original classification conflicts with declared third-party content"
        )
    if kind in ("commissioned", "licensed", "open_licensed") and not item["contains_third_party_content"]:
        # This is conservatively rejected rather than silently laundering
        # third-party rights into a supposedly self-created work.
        raise GameRightsError(
            "third-party license/source kind requires third-party content declaration"
        )

    if kind == "interoperability_research" and any(
        x in permissions for x in ("embed", "distribute", "commercial", "train")
    ):
        raise GameRightsError(
            "interoperability observations cannot be auto-promoted to distributable assets"
        )
    if kind == "user_supplied_unverified" and any(
        x in permissions for x in ("embed", "distribute", "commercial", "train")
    ):
        raise GameRightsError(
            "unverified user-supplied content lacks distributable/training rights evidence"
        )
    if kind != "original" and proof.lower() in ("none", "unknown", "self", "n/a"):
        raise GameRightsError("non-original sources require a meaningful license reference")
    return {
        "asset_id": name, "sha256": digest, "source_kind": kind,
        "licensor": licensor, "license_reference": proof,
        "allowed_uses": sorted(permissions),
        "contains_third_party_content": item["contains_third_party_content"],
        "contains_trademarks": item["contains_trademarks"],
        "contains_technological_protection": False,
    }


def admit_game_rights(
    manifest: Mapping[str, Any], *,
    action: str,
    jurisdiction: str,
) -> dict[str, Any]:
    """Issue a deterministic *attested, not legally verified* project receipt."""
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema_version", "project_id", "title", "rights_contact",
        "assets", "source_game_reference", "sdk_authorization",
    }:
        raise GameRightsError("project rights manifest schema is invalid")
    if manifest["schema_version"] != SCHEMA:
        raise GameRightsError("rights receipt version mismatch")
    project = _id(manifest["project_id"])
    title = manifest["title"]
    contact = manifest["rights_contact"]
    if (
        not isinstance(title, str) or not 1 <= len(title) <= MAX_TITLE
        or "\x00" in title
        or not isinstance(contact, str) or not 1 <= len(contact) <= 128
        or "\x00" in contact
    ):
        raise GameRightsError("project rights contact/title is invalid")
    if jurisdiction not in _JURISDICTIONS or action not in _ACTIONS:
        raise GameRightsError("action or jurisdiction is unspecified")
    assets = manifest["assets"]
    if not isinstance(assets, list) or not 1 <= len(assets) <= MAX_ASSETS:
        raise GameRightsError("project requires 1-128 explicit asset provenance records")
    checked = [_source(asset) for asset in assets]
    if len({asset["asset_id"] for asset in checked}) != len(checked):
        raise GameRightsError("duplicate asset provenance identity")
    if len({asset["sha256"] for asset in checked}) != len(checked):
        raise GameRightsError("duplicate content identities require explicit deduplication")
    game = manifest["source_game_reference"]
    if game is not None and (
        not isinstance(game, str) or len(game) > 256 or "\x00" in game
    ):
        raise GameRightsError("source game reference must be bounded text or null")
    sdk = manifest["sdk_authorization"]
    if sdk is not None and (
        not isinstance(sdk, str) or not 4 <= len(sdk) <= 256
        or "\x00" in sdk
    ):
        raise GameRightsError("SDK authorization must be a bounded reference or null")
    required = {
        "original_game": {"embed"},
        "independent_mechanics": {"embed"},
        "modify_authorized": {"modify"},
        "interoperability_study": set(),
        "private_reproduction": {"modify"},
        "publish": {"embed", "distribute"},
        "train_on_assets": {"train"},
    }[action]
    for asset in checked:
        if not required.issubset(asset["allowed_uses"]):
            raise GameRightsError(
                "project asset permissions do not cover the requested action"
            )
    if action in ("original_game", "independent_mechanics") and game is not None:
        raise GameRightsError("original/independent development cannot embed a source-game dependency")
    if action == "independent_mechanics" and any(
        item["source_kind"] != "original" for item in checked
    ):
        raise GameRightsError("independent mechanics project cannot embed copied external assets")
    if action in ("modify_authorized", "private_reproduction") and game is None:
        raise GameRightsError("modified source project must identify the source game")
    if action == "interoperability_study" and any(
        item["source_kind"] != "interoperability_research" for item in checked
    ):
        raise GameRightsError("interoperability observations must stay segregated")
    if action == "publish" and any(
        item["contains_trademarks"] for item in checked
    ):
        raise GameRightsError("trademark-bearing publication needs separate reviewed authorization")
    if action == "publish" and any(
        item["source_kind"] in ("interoperability_research", "user_supplied_unverified")
        for item in checked
    ):
        raise GameRightsError("unreviewed research or user uploads cannot be published")
    canonical = {
        "schema_version": SCHEMA,
        "project_id": project, "title": title,
        "rights_contact": contact,
        "action": action, "jurisdiction": jurisdiction,
        "assets": sorted(checked, key=lambda x: x["asset_id"]),
        "source_game_reference": game,
        "sdk_authorization": sdk,
    }
    digest = hashlib.sha256(_canonical(canonical)).hexdigest()
    return {
        "schema_version": "skeleton.game.rights.receipt.v1",
        "manifest_sha256": digest,
        "project_id": project, "jurisdiction": jurisdiction,
        "action": action, "asset_count": len(checked),
        "all_licenses_independently_verified": False,
        "legal_compliance_certified": False,
        "human_legal_review_completed": False,
        "distribution_authorized": False,
        "training_authorized": False,
        "technology_circumvention_performed": False,
        "sdk_authorization_attested": sdk is not None,
        "requires_human_review_for_release": True,
        "source_kind_summary": sorted({x["source_kind"] for x in checked}),
        "rights_assertion_only": True,
    }


# This is an enforceable scope restriction for the *creative toolchain*,
# not a claim that all homebrew distribution is automatically lawful.
# Reference material may be studied separately; executable editors,
# importers, native previews and exporters MUST call this shared gate.
HOMEBREW_ACTIONS = frozenset({"original_game", "independent_mechanics"})
HOMEBREW_SOURCE = "original"


def admit_homebrew_project(
    manifest: Mapping[str, Any], *, action: str, jurisdiction: str,
) -> dict[str, Any]:
    """Permit only wholly original game content through creative outputs.

    Licenses, attribution, source hashes, claimed author ownership, and
    historical exemptions never turn extracted commercial game material
    into homebrew. This explicitly excludes authorized modification of
    *someone else's game* from the homebrew-only production path.
    """
    if action not in HOMEBREW_ACTIONS:
        raise GameRightsError(
            "game production is homebrew-only: no modification, copying, "
            "repackaging, reproduction, distribution of imported titles, "
            "interoperability data, or asset training"
        )
    if not isinstance(manifest, dict):
        raise GameRightsError("homebrew production requires an original rights manifest")
    if manifest.get("source_game_reference") is not None:
        raise GameRightsError(
            "homebrew project must not depend on an existing source game"
        )
    if manifest.get("sdk_authorization") is not None:
        raise GameRightsError(
            "homebrew asset creation is independent of SDK contracts; "
            "target-specific SDK access is reviewed separately"
        )
    assets = manifest.get("assets")
    if not isinstance(assets, list) or not assets:
        raise GameRightsError("homebrew requires explicit original asset identities")
    for asset in assets:
        if not isinstance(asset, dict):
            raise GameRightsError("invalid homebrew asset")
        if asset.get("source_kind") != HOMEBREW_SOURCE:
            raise GameRightsError(
                "homebrew-only production refuses third-party, licensed, "
                "open-licensed, derived, imported and research assets"
            )
        if any(asset.get(key) is not False for key in (
            "contains_third_party_content", "contains_trademarks",
            "contains_technological_protection",
        )):
            raise GameRightsError(
                "homebrew assets cannot contain third-party expression, "
                "trademarks or technical-protection content"
            )
    receipt = admit_game_rights(
        manifest, action=action, jurisdiction=jurisdiction,
    )
    if receipt["source_kind_summary"] != ["original"]:
        raise GameRightsError("homebrew provenance classification changed")
    return {
        **receipt,
        "homebrew_only": True,
        "existing_game_reproduction_allowed": False,
        "asset_import_from_commercial_games_allowed": False,
        "derived_commercial_game_allowed": False,
        "license_verified_by_cryptographic_hash": False,
        "originality_independently_verified": False,
    }


__all__ = ["SCHEMA", "GameRightsError", "admit_game_rights", "admit_homebrew_project", "HOMEBREW_ACTIONS"]
