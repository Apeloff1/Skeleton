"""Honest 169-target static decompilation/asset-analysis gap inventory.

A listed target is not an installed emulator, recognized playable ROM,
legally cleared game or guaranteed executable decompiler. Native frame
inspection is common-layer functionality only after installed core admission.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .game_emulator_catalog import canonical_targets

_CODE = {
    "nes": "nrom_6502_vectors_only",
    "game_boy": "sm83_fixed_bank_entry_only",
    "game_boy_color": "sm83_fixed_bank_entry_only",
    "game_boy_advance": "arm7tdmi_arm_state_only",
}
_ASSETS = {
    "nes": "confirmed_iNES_chr_rom_2bpp",
    "game_boy": "operator_declared_2bpp_candidates_only",
    "game_boy_color": "operator_declared_2bpp_candidates_only",
    "game_boy_advance": "operator_declared_4bpp_8bpp_candidates_only",
    "snes": "operator_declared_4bpp_candidates_only",
    "genesis": "operator_declared_4bpp_candidates_only",
    "master_system": "operator_declared_4bpp_candidates_only",
    "game_gear": "operator_declared_4bpp_candidates_only",
    "ps1": "separate_validated_TIM_resource_file_only",
}
_PACKAGES = {
    "windows_95":"pe_sections_no_x86_asm",
    "windows_xp":"pe_sections_no_x86_asm",
    "dos_8086":"dos_binary_no_static_decompiler",
    "dos_vga":"dos_binary_no_static_decompiler",
    "dreamcast":"elf_sections_only",
    "ps2":"elf_sections_only",
    "ps1":"iso_root_and_TIM_aware_source_inventory",
}


def build_game_decompilation_target_matrix() -> dict[str, Any]:
    targets=canonical_targets()
    rows=[]
    for identity,metadata in sorted(targets.items()):
        cpu=metadata.get("cpu")
        output=metadata.get("output")
        source_code=_CODE.get(identity)
        decoded_assets=_ASSETS.get(identity)
        passive=_PACKAGES.get(identity)
        rows.append({
            "target_id":identity,
            "declared_cpu":cpu,
            "declared_output_format":output,
            "static_code_decoder":source_code or "not_implemented",
            "static_code_supported_subset":source_code is not None,
            "known_format_asset_decoder":decoded_assets or "not_implemented",
            "asset_source_region_verified":identity=="nes",
            "passive_file_container_inventory":passive or "generic_only_if_magic_recognized",
            "native_rgb_visual_analysis_if_installed_and_authorized":True,
            "native_core_or_game_detected_in_this_audit":False,
            "real_game_asset_training_or_quality_verified":False,
        })
    summary={
        "canonical_targets":len(rows),
        "static_code_decoder_target_families":sum(
            row["static_code_supported_subset"] for row in rows
        ),
        "known_format_asset_decoder_target_families":sum(
            row["known_format_asset_decoder"]!="not_implemented" for row in rows
        ),
        "validated_real_game_boots_in_this_audit":0,
        "production_game_model_weight_promotions_in_this_audit":0,
    }
    result={
        "schema_version":"skeleton.game.decompilation_target_gap_matrix.v1",
        "target_rows":rows,"summary":summary,
        "target_inventory_not_actual_running_emulator_count":True,
        "unimplemented_codecs_reported_explicitly":True,
    }
    result["matrix_sha256"]=hashlib.sha256(
        json.dumps(result,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
    ).hexdigest()
    return result
