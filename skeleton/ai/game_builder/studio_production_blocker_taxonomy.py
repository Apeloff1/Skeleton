"""Bounded, privacy-safe classification of actual studio E2E blockers.

Map operator-observed stage failures to specific, reviewable repair areas.
Do not persist raw compiler logs, tokens, arbitrary exception messages,
screenshots, licensed source, automatic retries or pseudo-training evidence.
"""
from __future__ import annotations

from .contracts import canonical_digest

SCHEMA = "skeleton.game_builder.production_blocker_taxonomy.v1"
STAGES = frozenset({"source", "rom", "emulator", "browser", "godot", "canvas"})
_EXACT = {
    "original_source_missing": ("source_checkpoint_missing", "Rebuild exact signed original source"),
    "source_not_yet_generated": ("source_checkpoint_missing", "Resume owned source-target checkpoint"),
    "pyboy_not_installed": ("gameboy_emulator_unavailable", "Provision PyBoy and rerun qualified GB/GBC ROM"),
    "fceux_not_installed": ("nes_emulator_unavailable", "Provision FCEUX and rerun qualified NROM"),
    "compiled_handheld_original_art_mismatch": (
        "compiled_sprite_mismatch", "Inspect RGBLINK tile labels and original 2bpp source bytes"
    ),
    "compiled_nes_chr_original_art_mismatch": (
        "compiled_sprite_mismatch", "Inspect the iNES CHR bank and original 2bpp source bytes"
    ),
    "native_cpu_checkpoint_state_mismatch": (
        "controller_or_gameplay_divergence", "Compare first GB/GBC CPU mismatch against the Python action trace"
    ),
    "nes_cpu_intermediate_checkpoint_mismatch": (
        "controller_or_gameplay_divergence", "Compare sampled NES zero-page state and source reference"
    ),
    "compiled_cartridge_diverged_from_reference_replay": (
        "controller_or_gameplay_divergence", "Inspect actual machine-code outcome and source trace"
    ),
    "nes_machine_code_diverged_from_reference_replay": (
        "controller_or_gameplay_divergence", "Inspect NROM 6502 control and level transitions"
    ),
    "rom_emulator_not_qualified": (
        "emulator_evidence_missing", "Run actual approved emulator playthrough on signed cartridge"
    ),
    "javascript_playthrough_not_qualified": (
        "browser_evidence_missing", "Execute generated offline JavaScript gameplay in a real Node VM"
    ),
    "godot_playthrough_not_qualified": (
        "godot_evidence_missing", "Run actual generated Godot game and inspect its headless replay"
    ),
    "generated_game_pixels_not_recorded": (
        "canvas_capture_missing", "Request separate consent for only the generated game's canvas"
    ),
    "native_assembler_adapter_missing": (
        "console_source_adapter_gap", "Implement and review target-specific original console assembler"
    ),
    "full_native_emulator_adapter_missing": (
        "console_emulator_adapter_gap", "Implement real CPU/controller replay for this console family"
    ),
}
_PREFIX = (
    ("toolchain_missing:", "compiler_unavailable", "Install approved original-game native compiler"),
    ("execution_exception:", "execution_exception", "Investigate bounded operator runtime exception"),
    ("native_build_", "native_compilation_failure", "Review verified assembler output and ROM header"),
)


def classify_production_blockers(events: list[dict], *, limit: int = 64) -> dict:
    if (type(events) is not list or len(events) > 512
            or type(limit) is not int or not 1 <= limit <= 128):
        raise ValueError("typed finite production E2E events and classification cap required")
    findings = []
    seen = set()
    omitted = 0
    for event in events:
        if type(event) is not dict or event.get("stage") not in STAGES:
            raise ValueError("only typed original studio stages may be classified")
        status = event.get("status")
        if status == "verified":
            continue
        if status not in ("blocked", "unsupported"):
            raise ValueError("invalid original game E2E stage status")
        raw = event.get("blocker")
        target = event.get("target")
        if (type(raw) is not str or not 1 <= len(raw) <= 256
                or type(target) is not str or not 1 <= len(target) <= 128):
            raise ValueError("bounded stage blocker and target identity required")
        category, remediation = _EXACT.get(raw, (
            "independent_reproduction_needed",
            "Reproduce the first failure with exact current source and independent runtime",
        ))
        for prefix, matched, suggestion in _PREFIX:
            if raw.startswith(prefix):
                category, remediation = matched, suggestion
                break
        key = (target, event["stage"], category)
        if key in seen:
            continue
        seen.add(key)
        if len(findings) >= limit:
            omitted += 1
            continue
        findings.append({
            "target": target, "stage": event["stage"],
            "category": category, "recommended_review": remediation,
            "operator_reproduction_required": True,
            "automatic_retry_authorized": False,
            "original_source_modified": False,
        })
    body = {
        "schema": SCHEMA, "classified_blockers": len(findings),
        "omitted_after_limit": omitted,
        "findings": findings,
        "trained_model_weights": False,
        "almanac_knowledge_promoted": False,
    }
    return {**body, "classification_digest": canonical_digest(body)}


__all__ = ["classify_production_blockers", "SCHEMA"]
