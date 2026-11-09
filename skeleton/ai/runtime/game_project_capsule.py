"""Legal-first, portable game project capsules and bounded map modifications.

Produces an engine-neutral ORIGINAL/rights-attested JSON project only:
no fake console binaries, emulators, SDK redistribution, decrypted ROMs,
BIOS images, third-party artworks, music, binaries or learned weights.
The capsule is an inspectable input for FUTURE separately approved
platform adapters. Author attestations do NOT constitute legal clearance.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .game_rights import GameRightsError, admit_homebrew_project
from .game_platform_catalog import GamePlatformError, plan_game_targets
from .gameplay_capabilities import GameplayError, compile_level, compile_native_scene
from .game_playability import check_game_playability

SCHEMA = "skeleton.game.portable_capsule.v1"
MAX_EDITS = 1024
MAX_PACKAGE_BYTES = 96 * 1024


class GameCapsuleError(ValueError):
    """Invalid source rights, game edits, target plans or capsule boundaries."""


def _canonical(obj: Any) -> bytes:
    try:
        return json.dumps(
            obj, ensure_ascii=True, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("ascii")
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise GameCapsuleError("game project has noncanonical values") from exc


def _admit_edits(
    tiles: list[str],
    edits: list[dict[str, Any]],
) -> list[str]:
    if not isinstance(edits, list) or len(edits) > MAX_EDITS:
        raise GameCapsuleError("tile modifications exceed 1024-cell budget")
    if not edits:
        return tiles[:]
    grid = [list(row) for row in tiles]
    visited: set[tuple[int, int]] = set()
    for edit in edits:
        if not isinstance(edit, dict) or set(edit) != {"x", "y", "tile"}:
            raise GameCapsuleError("each edit requires exactly x,y,tile")
        x, y, tile = edit["x"], edit["y"], edit["tile"]
        if (
            type(x) is not int or type(y) is not int
            or not 0 <= y < len(grid)
            or not 0 <= x < len(grid[0])
            or not isinstance(tile, str)
            or tile not in ("#", ".", "S", "G")
        ):
            raise GameCapsuleError("tile edit leaves the admitted coordinate or tile domain")
        key = x, y
        if key in visited:
            raise GameCapsuleError("tile edit conflict: same cell modified twice")
        visited.add(key)
        grid[y][x] = tile
    return ["".join(row) for row in grid]


def make_game_capsule(
    *,
    source_tiles: list[str],
    rights_manifest: Mapping[str, Any],
    target_ids: list[str],
    required_features: list[str],
    action: str,
    jurisdiction: str,
    edits: list[dict[str, Any]] | None = None,
    sdk_authorizations: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Author and plan a verified original/project-rights-attested scene.

    No native target binaries are produced. An SDK reference allows the
    catalog to show an attestation but NEVER unlocks a proprietary
    toolchain or certifies the rights to publish.
    """
    if (
        not isinstance(source_tiles, list)
        or any(not isinstance(line, str) for line in source_tiles)
        or not isinstance(rights_manifest, dict)
    ):
        raise GameCapsuleError("capsule must use explicit tile and rights data")
    if edits is None:
        edits = []
    try:
        initial = compile_level({"tiles": source_tiles})
        assets = rights_manifest.get("assets")
        if not isinstance(assets, list):
            raise GameCapsuleError("rights assets must be a list")
        tile_assets = [
            asset for asset in assets
            if isinstance(asset, dict) and asset.get("asset_id") == "tilemap"
        ]
        if (
            len(tile_assets) != 1
            or tile_assets[0].get("sha256") != initial["tile_digest"]
        ):
            raise GameCapsuleError(
                "tilemap rights record must match original source content digest"
            )
        admitted_rights = admit_homebrew_project(
            rights_manifest, action=action, jurisdiction=jurisdiction,
        )
        # The production path is original-homebrew ONLY. Editing another
        # author's licensed game, even with a user-provided license reference,
        # is not part of this pipeline. SDK access is independently scoped.
        if action not in ("original_game", "independent_mechanics"):
            raise GameCapsuleError("game creation and editing are homebrew-only")
        final_tiles = _admit_edits(source_tiles, edits)
        updated = compile_level({"tiles": final_tiles})
        if not updated["goal_reachable"]:
            raise GameCapsuleError("edited game must preserve a reachable goal")
        if updated["shortest_goal_steps"] is None:
            raise GameCapsuleError("game project cannot have an unreachable goal")
        scene = compile_native_scene({"tiles": final_tiles})
        real_playability = check_game_playability({
            "tiles": final_tiles, "max_frames": 96,
        })
        if scene["solid_tiles_covered"] != updated["solid_count"]:
            raise GameCapsuleError("scene collider coverage drift")
        plan = plan_game_targets(
            target_ids=target_ids,
            required_features=required_features,
            sdk_authorizations=sdk_authorizations,
        )
    except (GameRightsError, GamePlatformError, GameplayError) as exc:
        raise GameCapsuleError("game project failed admitted source or target checks") from exc

    content = {
        "schema_version": SCHEMA,
        "project_id": admitted_rights["project_id"],
        "source_tile_sha256": initial["tile_digest"],
        "edited_tile_sha256": updated["tile_digest"],
        "source_tilemap": list(source_tiles),
        "tilemap": list(final_tiles),
        "scene": scene,
        "target_plan": plan,
        # Keep the exact, bounded provenance statements for repeatable review.
        # A receipt digest without its referenced evidence is insufficient.
        "rights_manifest": json.loads(_canonical(rights_manifest)),
        "rights_receipt": admitted_rights,
        "modifications": list(edits),
        "action": action,
        "jurisdiction": jurisdiction,
        "playability": {
            "grid_goal_reachable": updated["goal_reachable"],
            "shortest_grid_steps": updated["shortest_goal_steps"],
            "actual_controller_replay_qualified": (
                real_playability["status"] == "playable"
            ),
            "controller_search_status": real_playability["status"],
            "controller_frames_if_playable": real_playability["controller_frames"],
            "controller_trace_sha256": real_playability["controls_sha256"],
            "real_hardware_validated": False,
        },
        "output_kind": "engine_neutral_json_project",
        "game_data_provenance_attested": True,
        "homebrew_only": True,
        "third_party_game_porting_supported": False,
        "legal_release_authorized": False,
        "external_binary_or_licensed_sdk_embedded": False,
        "console_rom_or_native_export_generated": False,
        "training_examples_added": 0,
    }
    raw = _canonical(content)
    if len(raw) > MAX_PACKAGE_BYTES:
        raise GameCapsuleError("universal game capsule exceeded 96 KiB")
    return {
        **content,
        "capsule_sha256": hashlib.sha256(raw).hexdigest(),
        "capsule_bytes": len(raw),
    }


def verify_game_capsule(capsule: Mapping[str, Any]) -> dict[str, Any]:
    """Verify project integrity and scene recomputation without source trust."""
    if not isinstance(capsule, dict):
        raise GameCapsuleError("game capsule must be an object")
    if set(capsule) != {
        "schema_version", "project_id", "source_tile_sha256",
        "edited_tile_sha256", "source_tilemap", "tilemap", "scene", "target_plan",
        "rights_manifest", "rights_receipt", "modifications", "action", "jurisdiction",
        "playability", "output_kind", "game_data_provenance_attested",
        "homebrew_only", "third_party_game_porting_supported",
        "legal_release_authorized",
        "external_binary_or_licensed_sdk_embedded",
        "console_rom_or_native_export_generated", "training_examples_added",
        "capsule_sha256", "capsule_bytes",
    }:
        raise GameCapsuleError("game capsule schema mismatch")
    body = {
        key: val for key, val in capsule.items()
        if key not in ("capsule_sha256", "capsule_bytes")
    }
    raw = _canonical(body)
    if len(raw) > MAX_PACKAGE_BYTES or len(raw) != capsule["capsule_bytes"]:
        raise GameCapsuleError("game capsule length mismatch")
    if hashlib.sha256(raw).hexdigest() != capsule["capsule_sha256"]:
        raise GameCapsuleError("game capsule checksum mismatch")
    if (
        capsule["schema_version"] != SCHEMA
        or capsule["output_kind"] != "engine_neutral_json_project"
        or capsule["legal_release_authorized"] is not False
        or capsule["external_binary_or_licensed_sdk_embedded"] is not False
        or capsule["console_rom_or_native_export_generated"] is not False
        or capsule["training_examples_added"] != 0
        or capsule["homebrew_only"] is not True
        or capsule["third_party_game_porting_supported"] is not False
    ):
        raise GameCapsuleError("game capsule attempted to claim unverified release")
    try:
        source = compile_level({"tiles": capsule["source_tilemap"]})
        replayed = _admit_edits(capsule["source_tilemap"], capsule["modifications"])
        scene = compile_native_scene({"tiles": capsule["tilemap"]})
        compiled = compile_level({"tiles": capsule["tilemap"]})
        replay_check = check_game_playability({
            "tiles": capsule["tilemap"], "max_frames": 96,
        })
    except (GameplayError, GameCapsuleError) as exc:
        raise GameCapsuleError("capsule tilemap cannot be compiled") from exc
    if (
        scene != capsule["scene"]
        or source["tile_digest"] != capsule["source_tile_sha256"]
        or replayed != capsule["tilemap"]
        or compiled["tile_digest"] != capsule["edited_tile_sha256"]
        or not compiled["goal_reachable"]
    ):
        raise GameCapsuleError("capsule native scene or source tile hash mismatch")
    gameplay = capsule["playability"]
    if (
        not isinstance(gameplay, dict)
        or gameplay != {
            "grid_goal_reachable": compiled["goal_reachable"],
            "shortest_grid_steps": compiled["shortest_goal_steps"],
            "actual_controller_replay_qualified": (
                replay_check["status"] == "playable"
            ),
            "controller_search_status": replay_check["status"],
            "controller_frames_if_playable": replay_check["controller_frames"],
            "controller_trace_sha256": replay_check["controls_sha256"],
            "real_hardware_validated": False,
        }
    ):
        raise GameCapsuleError("capsule controller-playability evidence changed")
    # Independently re-admit the embedded rights evidence and require the
    # specific source tilemap to remain content-identical. Re-signing JSON
    # cannot erase denied uses, downgrade third-party source kinds, or
    # quietly substitute a different "licensed" input.
    evidence = capsule["rights_manifest"]
    if not isinstance(evidence, dict):
        raise GameCapsuleError("capsule lacks inspectable rights provenance")
    try:
        fresh_rights = admit_homebrew_project(
            evidence, action=capsule["action"],
            jurisdiction=capsule["jurisdiction"],
        )
        source_assets = evidence["assets"]
        matching = [
            item for item in source_assets
            if item.get("asset_id") == "tilemap"
        ]
        if (
            len(matching) != 1
            or matching[0]["sha256"] != source["tile_digest"]
        ):
            raise GameCapsuleError(
                "embedded rights provenance does not identify this exact source"
            )
    except (GameRightsError, KeyError, TypeError, AttributeError) as exc:
        raise GameCapsuleError("capsule rights could not be re-admitted") from exc
    receipt = capsule["rights_receipt"]
    if receipt != fresh_rights:
        raise GameCapsuleError("capsule rights receipt differs from source evidence")
    if (
        not isinstance(receipt, dict)
        or receipt.get("project_id") != capsule["project_id"]
        or receipt.get("jurisdiction") != capsule["jurisdiction"]
        or receipt.get("action") != capsule["action"]
        or receipt.get("legal_compliance_certified") is not False
        or receipt.get("distribution_authorized") is not False
        or receipt.get("human_legal_review_completed") is not False
        or receipt.get("all_licenses_independently_verified") is not False
        or receipt.get("training_authorized") is not False
        or receipt.get("requires_human_review_for_release") is not True
        or receipt.get("rights_assertion_only") is not True
        or receipt.get("technology_circumvention_performed") is not False
        or not isinstance(receipt.get("manifest_sha256"), str)
        or len(receipt["manifest_sha256"]) != 64
    ):
        raise GameCapsuleError("capsule has incompatible rights receipt")
    # Rebuild every advertised platform row from the checked-in catalog.
    # Merely changing self-hashes must not turn a design-only target into a
    # fake validated PlayStation/Nintendo/Xbox exporter.
    plan = capsule["target_plan"]
    if (
        not isinstance(plan, dict)
        or plan.get("design_only") is not True
        or plan.get("native_binaries_ready") != 0
        or plan.get("rom_images_created") != 0
        or not isinstance(plan.get("targets"), list)
        or not plan["targets"]
        or not isinstance(plan["targets"][0], dict)
    ):
        raise GameCapsuleError("capsule claimed unsupported native platform readiness")
    try:
        requested = plan["targets"][0]["requested_features"]
        expected_plan = plan_game_targets(
            target_ids=[row["id"] for row in plan["targets"]],
            required_features=requested,
            sdk_authorizations={
                row["id"]: "attested-not-independently-verified"
                for row in plan["targets"] if row["sdk_reference_attested"] is True
            },
        )
    except (KeyError, TypeError, GamePlatformError) as exc:
        raise GameCapsuleError("capsule platform planning identity is invalid") from exc
    if expected_plan != plan:
        raise GameCapsuleError("capsule target plan differs from authenticated registry")
    return {
        "schema_version": "skeleton.game.portable_capsule.verify.v1",
        "capsule_sha256": capsule["capsule_sha256"],
        "project_id": capsule["project_id"],
        "scene_recomputed": True,
        "rights_attested_but_not_independently_verified": True,
        "target_native_binaries_built": 0,
        "legal_publication_approved": False,
        "training_examples_added": 0,
        "homebrew_only": True,
    }


__all__ = [
    "SCHEMA", "GameCapsuleError", "make_game_capsule",
    "verify_game_capsule",
]
