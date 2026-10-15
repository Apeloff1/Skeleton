"""Rights-bound, passive game decompilation and resource-analysis entrypoint.

A complete source tree cannot generally be recreated from compiled games.
This system provides bounded real binary disassembly, known-format asset
decoding and traceable original-game design findings. Caller-owned authority
is required for EACH operation, not just a user-provided license label.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .game_decompilation_archives import analyze_zip_project
from .game_decompilation_assets import decode_tile_region, extract_nes_chr
from .game_decompilation_code import disassemble_gb_sm83, disassemble_nes_nrom
from .game_decompilation_formats import inspect_binary_structure
from .game_decompilation_quality import derive_game_quality_brief
from .game_learning_ingestion import _parse_rom, _has_rom_signature

REPORT_SCHEMA = "skeleton.game.authorized_decompilation.v1"
MAX_GAME_BYTES = 32 * 1024 * 1024
MAX_CANDIDATES = 4
SCOPE_STRUCTURE = "inspect_structure"
SCOPE_CODE = "reverse_engineer_code"
SCOPE_ASSETS = "decode_assets"
SCOPE_PREVIEWS = "export_asset_previews"
SCOPE_QUALITY = "derive_quality_features"
SCOPE_SHADOW = "human_labeled_shadow_training"
SCOPES = frozenset((SCOPE_STRUCTURE, SCOPE_CODE, SCOPE_ASSETS, SCOPE_PREVIEWS, SCOPE_QUALITY, SCOPE_SHADOW))
ROM_EXTENSIONS = frozenset((
    ".nes", ".gb", ".gbc", ".gba", ".sfc", ".smc", ".gen", ".md", ".smd",
    ".z64", ".v64", ".n64", ".a78", ".lnx", ".sms", ".gg", ".nds", ".pbp",
))
_SHA = re.compile(r"^[0-9a-f]{64}$")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


@dataclass(frozen=True, slots=True)
class GameDecompilationGrant:
    source_sha256: str
    rights_evidence_digest: str
    principal_ref: str
    approved_scopes: tuple[str, ...]
    rights_acknowledged: bool = False

    def __post_init__(self) -> None:
        if (type(self.source_sha256) is not str or not _SHA.fullmatch(self.source_sha256)
            or type(self.rights_evidence_digest) is not str
            or not _SHA.fullmatch(self.rights_evidence_digest)
            or type(self.principal_ref) is not str
            or not _NAME.fullmatch(self.principal_ref)
            or type(self.rights_acknowledged) is not bool
            or not self.rights_acknowledged):
            raise ValueError("Source-bound explicit rights acknowledgement and accountable principal required")
        scopes = self.approved_scopes
        if (type(scopes) is not tuple or not 1 <= len(scopes) <= len(SCOPES)
            or len(set(scopes)) != len(scopes)
            or any(type(s) is not str or s not in SCOPES for s in scopes)):
            raise ValueError("Exactly defined, distinct rights scopes are required")


@dataclass(frozen=True, slots=True)
class DecompilationResult:
    report: dict[str, Any]
    previews: tuple[tuple[str, bytes], ...]

    def __post_init__(self) -> None:
        records = self.report.get("preview_artifacts", [])
        if len(records) != len(self.previews):
            raise ValueError("Returned preview receipts and private payloads differ")
        for record, item in zip(records, self.previews, strict=True):
            name, data = item
            if (name != record["name"] or _sha(data) != record["sha256"]
                or len(data) != record["size_bytes"]):
                raise ValueError("Preview artifact receipt no longer binds exact image bytes")


def _authorize(
    grant: GameDecompilationGrant, scope: str,
    authority: Callable[[str, GameDecompilationGrant], bool],
) -> None:
    if scope not in grant.approved_scopes:
        raise PermissionError("This exact game source lacks requested decompilation rights scope: " + scope)
    if not callable(authority) or authority(scope, grant) is not True:
        raise PermissionError("Trusted independent caller did not authorize scope: " + scope)


def _format(data: bytes, name: str) -> tuple[str, dict[str, Any]]:
    lowered = name.lower()
    if _has_rom_signature(data) or "." + lowered.rsplit(".", 1)[-1] in ROM_EXTENSIONS:
        parsed = _parse_rom(data, lowered)
        return parsed["format"], parsed
    passive = inspect_binary_structure(data, lowered)
    return passive["format"], passive


def decompile_authorized_game(
    data: bytes, filename: str, *,
    grant: GameDecompilationGrant,
    authorize: Callable[[str, GameDecompilationGrant], bool],
    inspect_code: bool = True,
    inspect_assets: bool = True,
    export_previews: bool = False,
    derive_quality: bool = True,
    candidate_tile_regions: Sequence[Mapping[str, Any]] = (),
    instruction_limit: int = 2048,
) -> DecompilationResult:
    """Analyze only source-bound, caller-authorized operations.

    A caller callback must affirm every requested scope at use-time; a
    grant alone is not independent verification of license or source rights.
    """
    if (type(data) is not bytes or not 1 <= len(data) <= MAX_GAME_BYTES
        or type(filename) is not str or not _NAME.fullmatch(filename)
        or type(grant) is not GameDecompilationGrant
        or type(inspect_code) is not bool or type(inspect_assets) is not bool
        or type(export_previews) is not bool or type(derive_quality) is not bool
        or type(instruction_limit) is not int or not 1 <= instruction_limit <= 4096
        or not isinstance(candidate_tile_regions, (tuple, list))
        or len(candidate_tile_regions) > MAX_CANDIDATES):
        raise ValueError("Source content, bounds, filename or requested analysis schema invalid")
    actual_sha = _sha(data)
    if actual_sha != grant.source_sha256:
        raise PermissionError("Grant is not bound to the exact supplied game source bytes")
    _authorize(grant, SCOPE_STRUCTURE, authorize)
    if inspect_code:
        _authorize(grant, SCOPE_CODE, authorize)
    if inspect_assets:
        _authorize(grant, SCOPE_ASSETS, authorize)
    if export_previews:
        if not inspect_assets:
            raise ValueError("Cannot export media previews without approved asset decoding")
        _authorize(grant, SCOPE_PREVIEWS, authorize)
    if derive_quality:
        _authorize(grant, SCOPE_QUALITY, authorize)
    if candidate_tile_regions and not inspect_assets:
        raise ValueError("Explicit tile candidates require approved asset inspection")
    for row in candidate_tile_regions:
        if not isinstance(row, dict) or set(row) != {"offset", "length", "codec"}:
            raise ValueError("Exact tile candidate requires offset, length and codec only")
    fmt, structure = _format(data, filename)
    previews: list[tuple[str, bytes]] = []
    code = None
    assets = None
    package = None
    candidate_rows = []
    if inspect_code:
        if fmt in ("ines", "nes2"):
            try:
                code = disassemble_nes_nrom(data, limit=instruction_limit)
                code["supported"] = True
            except ValueError:
                # Header may be valid while mapper-0 static layout is impossible.
                code = {"supported": False, "reason": "not_a_supported_NROM_memory_map",
                        "fabricated_source_code": False}
        elif fmt == "game_boy_cartridge":
            code = disassemble_gb_sm83(data, limit=instruction_limit)
            code["supported"] = True
        else:
            code = {"supported": False, "reason": "no_verified_disassembler_for_this_CPU_container",
                    "fabricated_source_code": False}
    if inspect_assets:
        if fmt in ("ines", "nes2"):
            assets, approved = extract_nes_chr(data, preview_authorized=export_previews)
            previews.extend(approved)
        elif fmt == "zip_container":
            package = analyze_zip_project(data)
        else:
            assets = {
                "supported": False,
                "reason": "no_known_exact_image_region_in_this_container",
                "arbitrary_ROM_bytes_not_reclassified_as_sprites": True,
            }
        for index, row in enumerate(candidate_tile_regions):
            analyzed, preview = decode_tile_region(
                data, offset=row["offset"], length=row["length"],
                codec=row["codec"], provenance="operator_declared_candidate",
                allow_png_export=export_previews,
            )
            candidate_rows.append(analyzed)
            if preview is not None:
                previews.append(("candidate_tile_" + str(index).zfill(2) + ".png", preview))
    artifact_receipts = [
        {"name": name, "sha256": _sha(raw), "size_bytes": len(raw),
         "content_kind": "synthetic_palette_preview_of_authorized_source_tiles"}
        for name, raw in previews
    ]
    if len({item["name"] for item in artifact_receipts}) != len(artifact_receipts):
        raise ValueError("Preview artifact names must be unique")
    body: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA,
        "input_filename": filename, "source_sha256": actual_sha,
        "source_size_bytes": len(data), "format": fmt,
        "structure": structure,
        "code_analysis": code, "asset_analysis": assets,
        "archive_resource_inventory": package,
        "declared_candidate_tile_regions": candidate_rows,
        "preview_artifacts": artifact_receipts,
        "provenance": {
            "principal_ref": grant.principal_ref,
            "rights_evidence_digest": grant.rights_evidence_digest,
            "acknowledgement_is_not_license_verification": True,
            "authorized_scopes": list(grant.approved_scopes),
            "independent_current_authorization_called": True,
        },
        "full_original_source_recovered": False,
        "native_executable_or_game_rom_executed": False,
        "gameplay_quality_or_decompilation_accuracy_independently_verified": False,
        "raw_source_bytes_in_report": False,
        "production_model_training_performed": False,
        "model_weights_updated": False,
    }
    if derive_quality:
        body["quality_brief"] = derive_game_quality_brief(
            game_format=fmt, source_sha256=actual_sha,
            rights_evidence_digest=grant.rights_evidence_digest,
            asset_analysis=assets, code_analysis=code, package_analysis=package,
        )
    body["report_sha256"] = _sha(_canonical(body))
    if len(_canonical(body)) > 8 * 1024 * 1024:
        raise ValueError("Decompilation report exceeds bounded eight-MiB evidence contract")
    return DecompilationResult(body, tuple(previews))

def analyze_authorized_native_frames(
    frames: Sequence[tuple[Mapping[str, Any], bytes]], *,
    grant: GameDecompilationGrant,
    authorize: Callable[[str, GameDecompilationGrant], bool],
    core_binary_sha256: str,
) -> dict[str, Any]:
    """Bounded genuine native framebuffer measurements for any libretro core.

    Frames must be captured by the legitimate emulator host separately.
    This analyzer does not call retro_run or scrape game RAM.
    """
    from .game_decompilation_runtime import observe_native_frames

    if not isinstance(grant, GameDecompilationGrant):
        raise PermissionError("Native pixel analysis requires source-bound rights grant")
    _authorize(grant, SCOPE_STRUCTURE, authorize)
    _authorize(grant, SCOPE_ASSETS, authorize)
    return observe_native_frames(
        frames,
        game_content_sha256=grant.source_sha256,
        core_binary_sha256=core_binary_sha256,
        rights_evidence_digest=grant.rights_evidence_digest,
        authorize=lambda: authorize(SCOPE_ASSETS, grant) is True,
    )


def prepare_reviewed_training_candidate(
    result: DecompilationResult, *, grant: GameDecompilationGrant,
    authorize: Callable[[str, GameDecompilationGrant], bool],
    human_score: int, reviewer_ref: str, label_evidence_digest: str,
) -> dict[str, Any]:
    """Human-label original measured features; never store recovered game assets."""
    from .game_decompilation_learning import make_human_labeled_candidate

    if (not isinstance(result, DecompilationResult)
        or not isinstance(grant, GameDecompilationGrant)
        or result.report.get("source_sha256") != grant.source_sha256
        or result.report.get("provenance", {}).get("rights_evidence_digest") != grant.rights_evidence_digest
        or result.report.get("schema_version") != REPORT_SCHEMA):
        raise PermissionError("Labeled asset learning must bind the exact source/grant")
    _authorize(grant, SCOPE_SHADOW, authorize)
    brief = result.report.get("quality_brief")
    if not isinstance(brief, dict):
        raise ValueError("No exact numeric human-review brief exists for this authorized source")
    return make_human_labeled_candidate(
        brief, score=human_score, reviewer_ref=reviewer_ref,
        label_evidence_digest=label_evidence_digest,
        training_rights_digest=grant.rights_evidence_digest,
        authorize=lambda: authorize(SCOPE_SHADOW, grant) is True,
    )
