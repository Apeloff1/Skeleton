"""Source-bound studio qualification ledger for actual multi-console campaigns.

This is a read-side assurance projection over the canonical campaign receipts,
plus a deliberately separate, explicit operator-only native ROM build action.
It does not grant Jeeves shell/toolchain execution, emulate cartridges, assess
IP rights, approve publication, or treat Dragon notes as model improvements.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from .contracts import canonical_digest
from .studio_build_qualification import (
    NativeBuildQualificationError,
    _BUILD_ADAPTERS, _header, _regular, _verify_source, qualify_native_build,
    parse_game_boy_symbols, parse_nes_labels,
)
from .studio_campaign import (
    CampaignOrder, StudioCampaignError,
    _atomic_json, _inspect_campaign_unlocked, _load_json, _verify_target,
)
from .studio_campaign_lock import campaign_lock
from .studio_runtime_qualification import _inputs as _browser_inputs, qualify_browser_gameplay
from .studio_godot_qualification import godot_inputs, qualify_godot_headless
from .studio_pixel_parity import inspect_cross_engine_pixels
from .studio_game_boy_emulator import qualify_game_boy_emulator
from .studio_nes_emulator import qualify_nes_cpu_ppu
from .studio_nes_chr_parity import NESCHRIntegrityError, inspect_compiled_nes_chr
from .studio_dragon_canvas_capture import capture_generated_game, _png_geometry

SCHEMA = "skeleton.game_builder.production_assurance.v1"
QUALIFICATION_SCHEMA = "skeleton.game_builder.campaign_rom_evidence.v1"
GATES = (
    "original_world_source",
    "replay_proof_source",
    "indexed_sprites_and_descriptors",
    "browser_engine_source",
    "godot_engine_source",
    "native_platform_source",
    "exact_source_attestation",
    "cross_engine_pixel_art_parity",
    "native_rom_compiled",
    "cartridge_structure_checked",
    "browser_javascript_playthrough_executed",
    "godot_headless_playthrough_executed",
    "generated_game_canvas_frames_recorded",
    "emulator_playthrough_executed",
    "controller_response_verified",
    "visual_and_audio_runtime_qualified",
    "rights_and_license_review_approved",
    "dragon_knowledge_review_approved",
    "extended_recovery_endurance_qualified",
    "release_signoff",
)
SOURCE_GATES = frozenset(GATES[:7])
PARITY_GATE = "cross_engine_pixel_art_parity"
BROWSER_GATE = "browser_javascript_playthrough_executed"
GODOT_GATE = "godot_headless_playthrough_executed"
CANVAS_GATE = "generated_game_canvas_frames_recorded"
EMULATOR_GATE = "emulator_playthrough_executed"
EMU_CONTROLLER_GATE = "controller_response_verified"
NATIVE_GATES = frozenset(GATES[8:10])


class StudioAssuranceError(ValueError):
    """A production claim lacks matching exact-source or executable evidence."""


def _relative_rom(root: Path, target: str) -> Path:
    return root / "qualifications" / target / "qualified.rom"


def _qualification_receipt(root: Path, target: str, source_identity: str) -> dict | None:
    directory = root / "qualifications" / target
    record_file = directory / "qualification.json"
    if not record_file.exists():
        if _relative_rom(root, target).exists():
            raise StudioAssuranceError("binary exists without authoritative build receipt")
        return None
    if directory.is_symlink() or record_file.is_symlink():
        raise StudioAssuranceError("qualification symlink is not acceptable evidence")
    record = _load_json(record_file)
    if (record.get("schema") != QUALIFICATION_SCHEMA or
            record.get("target") != target or
            record.get("source_identity") != source_identity):
        raise StudioAssuranceError("compiled cartridge is not bound to current project")
    if canonical_digest({k: v for k, v in record.items()
                         if k != "evidence_digest"}) != record.get("evidence_digest"):
        raise StudioAssuranceError("qualified binary record has changed")
    evidence = record.get("build")
    if (not isinstance(evidence, dict) or evidence.get("target") != target
            or evidence.get("binary_built") is not True
            or evidence.get("rom_header_verified") is not True
            or evidence.get("tools_invoked") is not True):
        raise StudioAssuranceError("claimed compilation lacks executed native build receipt")
    if canonical_digest({k: v for k, v in evidence.items()
                         if k != "receipt_digest"}) != evidence.get("receipt_digest"):
        raise StudioAssuranceError("toolchain result digest mismatch")
    source = root / "targets" / target
    try:
        _, actual_source = _verify_source(source, target)
    except (NativeBuildQualificationError, OSError) as exc:
        raise StudioAssuranceError("native source changed after compilation") from exc
    if actual_source != evidence.get("source_digest"):
        raise StudioAssuranceError("compiled binary is bound to a different source revision")
    artifact = _relative_rom(root, target)
    if artifact.is_symlink():
        raise StudioAssuranceError("compiled ROM must not be a symlink")
    try:
        body = _regular(artifact, 8 * 1024 * 1024)
        _header(_BUILD_ADAPTERS[target][4], body)
    except (NativeBuildQualificationError, OSError) as exc:
        raise StudioAssuranceError("compiled ROM bytes or header are invalid") from exc
    if (sha256(body).hexdigest() != evidence.get("binary_sha256")
            or len(body) != evidence.get("binary_size")):
        raise StudioAssuranceError("ROM differs from the recorded toolchain output")
    if target == "nintendo_famicom":
        try:
            inspect_compiled_nes_chr(body, root / "targets" / target)
        except NESCHRIntegrityError as exc:
            raise StudioAssuranceError("actual NES cartridge original sprites differ from source") from exc
    if target in ("nintendo_game_boy", "nintendo_game_boy_color", "nintendo_famicom"):
        map_file = artifact.with_suffix(".sym")
        try:
            raw_symbols = _regular(map_file, 128_000)
            (parse_nes_labels(raw_symbols) if target == "nintendo_famicom"
             else parse_game_boy_symbols(raw_symbols))
        except (OSError, ValueError) as exc:
            raise StudioAssuranceError("RGBDS game engine symbol map unavailable") from exc
        if sha256(raw_symbols).hexdigest() != evidence.get("symbol_sha256"):
            raise StudioAssuranceError("ROM WRAM debug symbols differ from compilation")
    return record


def qualify_campaign_target(
    order: CampaignOrder, root: str | Path, target: str, *,
    authorized: bool, execute: bool, timeout_seconds: int = 45,
) -> dict:
    """Compile exactly one completed target with an operator-authorized toolchain.

    Successful ROMs and evidence live outside the immutable source bundle;
    qualified, denied, unsupported and missing-toolchain states are distinct.
    """
    if authorized is not True:
        raise PermissionError("native compilation must have local operator authorization")
    if execute is not True:
        raise StudioAssuranceError("compilation requires an explicit execute opt-in")
    if not isinstance(order, CampaignOrder) or target not in order.targets:
        raise StudioAssuranceError("target does not belong to typed campaign")
    if target not in _BUILD_ADAPTERS:
        raise StudioAssuranceError("no bounded toolchain adapter for this console")
    base = Path(root)
    with campaign_lock(base):
        state = _inspect_campaign_unlocked(order, base)
        if target not in state["completed_targets"]:
            raise StudioAssuranceError("source stage must have exact verified completion")
        identity = state["identity"]
        previous = _qualification_receipt(base, target, identity)
        if previous is not None:
            return {
                "target": target, "native_rom_compiled": True,
                "already_qualified": True,
                "evidence_digest": previous["evidence_digest"],
                "source_identity": identity,
            }
        target_dir = base / "qualifications" / target
        if target_dir.is_symlink():
            raise StudioAssuranceError("native output cannot be a symlink")
        target_dir.mkdir(parents=True, exist_ok=True)
        output = _relative_rom(base, target)
        if output.exists() or output.is_symlink():
            raise StudioAssuranceError("unreceipted native ROM may not be overwritten")
        result = qualify_native_build(
            base / "targets" / target, target, authorized=True,
            execute=True, output=output, timeout_seconds=timeout_seconds,
            output_symbols=output.with_suffix(".sym"),
        )
        receipt = result.as_receipt()
        if not result.binary_built or not result.rom_header_verified:
            return {
                "target": target, "native_rom_compiled": False,
                "already_qualified": False,
                "blocker": result.blocker,
                "toolchain_available": result.toolchain_available,
                "tools_invoked": result.tools_invoked,
                "source_identity": identity,
                "model_training_performed": False,
            }
        if target == "nintendo_famicom":
            try:
                inspect_compiled_nes_chr(_regular(output, 8 * 1024 * 1024),
                                         base / "targets" / target)
            except (NESCHRIntegrityError, OSError, ValueError):
                # The binary was published by this exclusive, lock-held build,
                # but the actual compiled CHR bytes diverged. Reclaim only
                # the just-produced output after verifying its own SHA.
                if sha256(_regular(output, 8 * 1024 * 1024)).hexdigest() != result.binary_sha256:
                    raise StudioAssuranceError("unexpected ROM mutation during CHR rejection")
                output.unlink()
                output.with_suffix(".sym").unlink()
                return {
                    "target": target, "native_rom_compiled": False,
                    "blocker": "compiled_nes_chr_original_art_mismatch",
                    "source_identity": identity, "model_training_performed": False,
                }
        body = {
            "schema": QUALIFICATION_SCHEMA, "target": target,
            "source_identity": identity,
            "build": receipt,
            "emulator_playthrough_verified": False,
            "hardware_controller_qualified": False,
            "publication_authorized": False,
        }
        record = {**body, "evidence_digest": canonical_digest(body)}
        _atomic_json(target_dir / "qualification.json", record)
        _qualification_receipt(base, target, identity)
        return {
            "target": target, "native_rom_compiled": True,
            "already_qualified": False,
            "binary_sha256": receipt["binary_sha256"],
            "evidence_digest": record["evidence_digest"],
            "source_identity": identity,
            "emulator_playthrough_verified": False,
            "hardware_controller_qualified": False,
            "publication_authorized": False,
        }


def _browser_receipt(root: Path, target: str, source_identity: str) -> dict | None:
    folder = root / "qualifications" / target
    record_path = folder / "browser_qualification.json"
    if not record_path.exists():
        return None
    if record_path.is_symlink() or folder.is_symlink():
        raise StudioAssuranceError("browser qualification contains a source symlink")
    record = _load_json(record_path)
    if (record.get("schema") != "skeleton.game_builder.campaign_browser_evidence.v1"
            or record.get("target") != target
            or record.get("source_identity") != source_identity):
        raise StudioAssuranceError("browser runtime proof belongs to another campaign")
    if canonical_digest({k: v for k, v in record.items()
                         if k != "evidence_digest"}) != record.get("evidence_digest"):
        raise StudioAssuranceError("browser evidence hash does not match")
    proof = record.get("runtime")
    if (type(proof) is not dict or proof.get("winning_replay_verified") is not True
            or proof.get("javascript_executed") is not True
            or proof.get("release_ready") is not False):
        raise StudioAssuranceError("browser runtime gate lacks executed winning proof")
    if canonical_digest({k: v for k, v in proof.items()
                         if k != "receipt_digest"}) != proof.get("receipt_digest"):
        raise StudioAssuranceError("browser execution receipt is corrupt")
    try:
        html, gameplay, world = _browser_inputs(root / "targets" / target / "engines")
    except (OSError, ValueError) as exc:
        raise StudioAssuranceError("qualified browser source is missing or changed") from exc
    if (proof.get("world_digest") != world
            or proof.get("html_sha256") != sha256(html).hexdigest()
            or proof.get("proof_sha256") != sha256(gameplay).hexdigest()):
        raise StudioAssuranceError("JS gameplay evidence bound to an old source revision")
    return record


def qualify_campaign_browser(
    order: CampaignOrder, root: str | Path, target: str, *,
    authorized: bool, execute: bool, timeout_seconds: int = 30,
) -> dict:
    """Run the exact generated JS gameplay trace, never simulate a real browser."""
    if authorized is not True:
        raise PermissionError("JS gameplay execution requires an operator decision")
    if execute is not True:
        raise StudioAssuranceError("actual JS execution needs explicit opt-in")
    if not isinstance(order, CampaignOrder) or target not in order.targets:
        raise StudioAssuranceError("original production target not in campaign")
    base = Path(root)
    with campaign_lock(base):
        campaign = _inspect_campaign_unlocked(order, base)
        if target not in campaign["completed_targets"]:
            raise StudioAssuranceError("source must exist before JS execution")
        earlier = _browser_receipt(base, target, campaign["identity"])
        if earlier is not None:
            return {"target": target, "already_qualified": True,
                    "javascript_gameplay_executed": True,
                    "evidence_digest": earlier["evidence_digest"]}
        result = qualify_browser_gameplay(
            base / "targets" / target / "engines",
            authorized=True, execute=True, timeout_seconds=timeout_seconds,
        )
        evidence = result.as_receipt()
        if not result.winning_replay_verified:
            return {"target": target, "javascript_gameplay_executed": False,
                    "failure": result.failure, "node_available": result.node_available,
                    "graphical_browser_pixels_verified": False}
        folder = base / "qualifications" / target
        if folder.is_symlink():
            raise StudioAssuranceError("qualification directory cannot be a symlink")
        folder.mkdir(parents=True, exist_ok=True)
        body = {
            "schema": "skeleton.game_builder.campaign_browser_evidence.v1",
            "source_identity": campaign["identity"],
            "target": target,
            "runtime": evidence,
            "actual_graphical_browser_execution": False,
            "native_godot_execution": False,
            "release_authorized": False,
        }
        record = {**body, "evidence_digest": canonical_digest(body)}
        _atomic_json(folder / "browser_qualification.json", record)
        _browser_receipt(base, target, campaign["identity"])
        return {"target": target, "already_qualified": False,
                "javascript_gameplay_executed": True,
                "evidence_digest": record["evidence_digest"],
                "graphical_browser_pixels_verified": False}


def _godot_receipt(root: Path, target: str, source_identity: str) -> dict | None:
    base = root / "qualifications" / target
    record_path = base / "godot_qualification.json"
    if not record_path.exists():
        return None
    if base.is_symlink() or record_path.is_symlink():
        raise StudioAssuranceError("Godot evidence may not be a symlink")
    record = _load_json(record_path)
    if (record.get("schema") != "skeleton.game_builder.campaign_godot_evidence.v1"
            or record.get("target") != target
            or record.get("source_identity") != source_identity
            or canonical_digest({k: v for k, v in record.items()
                                 if k != "evidence_digest"}) != record.get("evidence_digest")):
        raise StudioAssuranceError("Godot evidence differs from current campaign")
    proof = record.get("runtime")
    if (not isinstance(proof, dict)
            or proof.get("engine_executed") is not True
            or proof.get("game_winning_replay_verified") is not True
            or proof.get("graphical_framebuffer_verified") is not False
            or canonical_digest({k: v for k, v in proof.items()
                                 if k != "receipt_digest"}) != proof.get("receipt_digest")):
        raise StudioAssuranceError("Godot execution record lacks a valid winning proof")
    try:
        _, world, steps, current = godot_inputs(root / "targets" / target / "engines")
    except (ValueError, OSError) as exc:
        raise StudioAssuranceError("qualified native engine sources no longer valid") from exc
    if (proof.get("world_digest") != world
            or proof.get("source_identity") != current
            or proof.get("action_count") != steps):
        raise StudioAssuranceError("Godot replay was executed for a different source")
    return record


def qualify_campaign_godot(
    order: CampaignOrder, root: str | Path, target: str, *,
    authorized: bool, execute: bool, timeout_seconds: int = 45,
) -> dict:
    """Run real Godot headless replay without modifying immutable project source."""
    if authorized is not True:
        raise PermissionError("actual Godot binary invocation requires operator authority")
    if execute is not True:
        raise StudioAssuranceError("Godot runtime needs explicit execute intent")
    if not isinstance(order, CampaignOrder) or target not in order.targets:
        raise StudioAssuranceError("original campaign target required")
    base = Path(root)
    with campaign_lock(base):
        campaign = _inspect_campaign_unlocked(order, base)
        if target not in campaign["completed_targets"]:
            raise StudioAssuranceError("Godot source must exist before replay")
        earlier = _godot_receipt(base, target, campaign["identity"])
        if earlier is not None:
            return {"target": target, "already_qualified": True,
                    "godot_headless_gameplay_executed": True,
                    "evidence_digest": earlier["evidence_digest"]}
        result = qualify_godot_headless(
            base / "targets" / target / "engines", authorized=True,
            execute=True, timeout_seconds=timeout_seconds,
        )
        evidence = result.as_receipt()
        if not result.game_winning_replay_verified:
            return {"target": target, "godot_headless_gameplay_executed": False,
                    "failure": result.failure, "godot_available": result.godot_available,
                    "graphical_framebuffer_verified": False}
        folder = base / "qualifications" / target
        if folder.is_symlink():
            raise StudioAssuranceError("qualification target path is unsafe")
        folder.mkdir(parents=True, exist_ok=True)
        body = {
            "schema": "skeleton.game_builder.campaign_godot_evidence.v1",
            "source_identity": campaign["identity"], "target": target,
            "runtime": evidence, "graphical_framebuffer_verified": False,
            "native_export_signed": False, "release_authorized": False,
        }
        record = {**body, "evidence_digest": canonical_digest(body)}
        _atomic_json(folder / "godot_qualification.json", record)
        _godot_receipt(base, target, campaign["identity"])
        return {"target": target, "already_qualified": False,
                "godot_headless_gameplay_executed": True,
                "evidence_digest": record["evidence_digest"],
                "graphical_framebuffer_verified": False}


def _canvas_receipt(root: Path, target: str, source_identity: str) -> dict | None:
    folder = root / "qualifications" / target / "canvas_capture"
    manifest = folder / "capture.json"
    if not manifest.exists():
        return None
    if folder.is_symlink() or manifest.is_symlink():
        raise StudioAssuranceError("generated game capture may not be a symlink")
    record = _load_json(manifest)
    if (record.get("schema") != "skeleton.game_builder.dragon_generated_canvas_capture.v1"
            or record.get("source") != "actual_local_headless_browser_canvas_screenshots"
            or record.get("graphical_browser_pixels_observed") is not True
            or record.get("user_screen_recorded") is not False
            or record.get("model_training_authorized") is not False
            or record.get("dragon_knowledge_promoted") is not False
            or record.get("release_authorized") is not False):
        raise StudioAssuranceError("capture lacks explicit original-canvas-only evidence")
    if canonical_digest({k: v for k, v in record.items()
                         if k != "capture_digest"}) != record.get("capture_digest"):
        raise StudioAssuranceError("real game canvas manifest digest is corrupted")
    frames = record.get("frames")
    if (type(frames) is not dict or not 2 <= len(frames) <= 3
            or set(frames) != {f"frame_{i:02d}.png" for i in range(len(frames))}):
        raise StudioAssuranceError("browser canvas capture must contain bounded frames")
    for name, claim in frames.items():
        frame = folder / name
        if frame.is_symlink() or not frame.is_file():
            raise StudioAssuranceError("frameback evidence missing or replaced")
        blob = frame.read_bytes()
        try:
            _png_geometry(blob)
        except ValueError as exc:
            raise StudioAssuranceError("captured canvas PNG is corrupted") from exc
        if (type(claim) is not dict or claim.get("sha256") != sha256(blob).hexdigest()
                or claim.get("bytes") != len(blob)):
            raise StudioAssuranceError("captured screenshot differs from reviewed frame hash")
    try:
        html, replay, world = _browser_inputs(root / "targets" / target / "engines")
    except (ValueError, OSError) as exc:
        raise StudioAssuranceError("canvas capture's original HTML source is not current") from exc
    if (record.get("world_digest") != world
            or record.get("html_sha256") != sha256(html).hexdigest()
            or record.get("proof_sha256") != sha256(replay).hexdigest()):
        raise StudioAssuranceError("canvas capture belongs to a different game source revision")
    return record


def qualify_campaign_canvas(
    order: CampaignOrder, root: str | Path, target: str, *,
    authorized: bool, capture_consent: bool, execute: bool,
    timeout_seconds: int = 60,
) -> dict:
    """Capture actual browser-generated game pixels with explicit local consent."""
    if authorized is not True or capture_consent is not True:
        raise PermissionError("operator must explicitly approve original-game frame capture")
    if execute is not True:
        raise StudioAssuranceError("actual Chromium capture requires explicit run intent")
    if not isinstance(order, CampaignOrder) or target not in order.targets:
        raise StudioAssuranceError("original game target not in campaign")
    base = Path(root)
    with campaign_lock(base):
        current = _inspect_campaign_unlocked(order, base)
        if target not in current["completed_targets"]:
            raise StudioAssuranceError("source must be verified before image observation")
        earlier = _canvas_receipt(base, target, current["identity"])
        if earlier is not None:
            return {
                "target": target, "already_qualified": True,
                "generated_game_canvas_recorded": True,
                "evidence_digest": earlier["capture_digest"],
                "model_training_authorized": False,
            }
        folder = base / "qualifications" / target
        if folder.is_symlink():
            raise StudioAssuranceError("qualification destination may not be a symlink")
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / "canvas_capture"
        if dest.exists() or dest.is_symlink():
            raise StudioAssuranceError("unverified capture already occupies output")
        result = capture_generated_game(
            base / "targets" / target / "engines", dest,
            authorized=True, capture_consent=True,
            execute=True, timeout_seconds=timeout_seconds,
        )
        if result.get("graphical_browser_pixels_observed") is not True:
            return {
                "target": target, "generated_game_canvas_recorded": False,
                "blocker": result.get("blocker", "capture_unavailable"),
                "model_training_authorized": False,
            }
        verified = _canvas_receipt(base, target, current["identity"])
        if verified is None:
            raise StudioAssuranceError("saved canvas record was not verifiable")
        return {
            "target": target, "generated_game_canvas_recorded": True,
            "already_qualified": False,
            "evidence_digest": verified["capture_digest"],
            "model_training_authorized": False,
            "user_screen_recorded": False,
        }


def _emulator_receipt(root: Path, target: str, source_identity: str) -> dict | None:
    folder = root / "qualifications" / target
    receipt_path = folder / "emulator_qualification.json"
    if not receipt_path.exists():
        return None
    if folder.is_symlink() or receipt_path.is_symlink():
        raise StudioAssuranceError("native emulator evidence may not be a symlink")
    proof = _load_json(receipt_path)
    if (proof.get("schema") != "skeleton.game_builder.campaign_emulator_evidence.v1"
            or proof.get("target") != target
            or proof.get("source_identity") != source_identity
            or canonical_digest({k: v for k, v in proof.items()
                                 if k != "evidence_digest"}) != proof.get("evidence_digest")):
        raise StudioAssuranceError("native emulator receipt belongs to another campaign")
    run = proof.get("run")
    nes = target == "nintendo_famicom"
    schema = ("skeleton.game_builder.nes_cpu_ppu_playthrough.v1" if nes
              else "skeleton.game_builder.game_boy_emulator_playthrough.v1")
    replay_key = "cpu_input_replay_executed" if nes else "full_controller_replay"
    frame_key = "frame_count" if nes else "frames_advanced"
    if (type(run) is not dict
            or run.get("schema") != schema
            or run.get("emulator_executed") is not True
            or run.get(replay_key) is not True
            or run.get("machine_code_victory") is not True
            or run.get("physical_controller_verified") is not False
            or run.get("physical_console_verified") is not False
            or type(run.get(frame_key)) is not int
            or run[frame_key] <= 0
            or canonical_digest({k: v for k, v in run.items()
                                 if k != "receipt_digest"}) != run.get("receipt_digest")):
        raise StudioAssuranceError("native ROM playthrough evidence lacks real machine-code victory")
    compiled = _qualification_receipt(root, target, source_identity)
    if compiled is None:
        raise StudioAssuranceError("emulator replay lacks independent compiled ROM evidence")
    compiled_info = compiled["build"]
    if (run.get("rom_sha256") != compiled_info.get("binary_sha256")
            or run.get("symbols_sha256") != compiled_info.get("symbol_sha256")):
        raise StudioAssuranceError("emulator proof is not for exact native ROM and symbols")
    try:
        _, gameplay, world = _browser_inputs(root / "targets" / target / "engines")
    except (OSError, ValueError) as exc:
        raise StudioAssuranceError("emulator proof's original Python game is no longer valid") from exc
    if (run.get("world_digest") != world
            or run.get("proof_sha256") != sha256(gameplay).hexdigest()):
        raise StudioAssuranceError("emulator memory replay mismatched canonical source game")
    return proof


def qualify_campaign_emulator(
    order: CampaignOrder, root: str | Path, target: str, *,
    authorized: bool, execute: bool, timeout_seconds: int = 90,
    max_frames: int = 260_000,
) -> dict:
    """Execute validated GB/GBC PyBoy or NES FCEUX machine-code controller replay."""
    if authorized is not True:
        raise PermissionError("local emulator execution requires explicit operator authority")
    if execute is not True:
        raise StudioAssuranceError("native cartridge emulation requires opt-in execution")
    if not isinstance(order, CampaignOrder) or target not in order.targets:
        raise StudioAssuranceError("emulated target is not in canonical original game campaign")
    if target not in ("nintendo_game_boy", "nintendo_game_boy_color", "nintendo_famicom"):
        raise StudioAssuranceError("no full cartridge emulator replay adapter for target")
    base = Path(root)
    with campaign_lock(base):
        campaign = _inspect_campaign_unlocked(order, base)
        if target not in campaign["completed_targets"]:
            raise StudioAssuranceError("original source must be checkpointed before emulator run")
        compiled = _qualification_receipt(base, target, campaign["identity"])
        if compiled is None:
            raise StudioAssuranceError("real binary toolchain must complete before emulator run")
        existing = _emulator_receipt(base, target, campaign["identity"])
        if existing is not None:
            return {
                "target": target, "already_qualified": True,
                "machine_code_victory": True,
                "evidence_digest": existing["evidence_digest"],
                "physical_controller_verified": False,
            }
        folder = base / "qualifications" / target
        engine = base / "targets" / target / "engines"
        if target == "nintendo_famicom":
            result = qualify_nes_cpu_ppu(
                folder, engine_source=engine,
                authorized=True, execute=True,
                timeout_seconds=timeout_seconds, max_frames=max_frames,
            )
        else:
            result = qualify_game_boy_emulator(
                folder, engine_source=engine, target=target,
                authorized=True, execute=True,
                timeout_seconds=timeout_seconds, max_frames=max_frames,
            )
        run = result.as_receipt()
        if not result.machine_code_victory:
            return {
                "target": target, "machine_code_victory": False,
                "emulator_available": result.emulator_available,
                "emulator_executed": result.emulator_executed,
                "blocker": result.blocker,
                "physical_controller_verified": False,
            }
        body = {
            "schema": "skeleton.game_builder.campaign_emulator_evidence.v1",
            "target": target, "source_identity": campaign["identity"],
            "run": run, "physical_controller_verified": False,
            "physical_hardware_verified": False,
            "release_authorized": False,
        }
        record = {**body, "evidence_digest": canonical_digest(body)}
        _atomic_json(folder / "emulator_qualification.json", record)
        _emulator_receipt(base, target, campaign["identity"])
        return {
            "target": target, "machine_code_victory": True,
            "already_qualified": False,
            "framebuffer_sha256": (
                result.ppu_frame_sha256 if target == "nintendo_famicom"
                else result.framebuffer_sha256
            ),
            "evidence_digest": record["evidence_digest"],
            "physical_controller_verified": False,
        }


def _inspect_production_assurance_unlocked(order: CampaignOrder, root: str | Path) -> dict:
    """Recheck real on-disk campaign artifacts and exact qualified binaries.

    Missing E2E, learning, permission, and release evidence always fails
    closed; a developer may not simply pass an 'all gates passed' dictionary.
    """
    if not isinstance(order, CampaignOrder):
        raise StudioAssuranceError("typed canonical campaign order required")
    base = Path(root)
    campaign = _inspect_campaign_unlocked(order, base)
    by_target = []
    passed = 0
    for target in order.targets:
        source = base / "targets" / target
        source_receipt = None
        if target in campaign["completed_targets"]:
            source_receipt = _verify_target(
                source, order.project_id, target, campaign["identity"],
            )
        binary = None
        browser = None
        godot = None
        emulator = None
        art_parity = None
        canvas = None
        if source_receipt is not None:
            if target in _BUILD_ADAPTERS:
                binary = _qualification_receipt(base, target, campaign["identity"])
            art_parity = inspect_cross_engine_pixels(source)
            emulator = (_emulator_receipt(base, target, campaign["identity"])
                        if target in ("nintendo_game_boy", "nintendo_game_boy_color",
                                      "nintendo_famicom") else None)
            browser = _browser_receipt(base, target, campaign["identity"])
            godot = _godot_receipt(base, target, campaign["identity"])
            canvas = _canvas_receipt(base, target, campaign["identity"])
        gates = {}
        for gate in GATES:
            if gate in SOURCE_GATES and source_receipt is not None:
                status, reason = "artifact_integrity_checked", None
            elif gate in NATIVE_GATES and binary is not None:
                status, reason = "binary_structure_checked", None
            elif gate in (EMULATOR_GATE, EMU_CONTROLLER_GATE) and emulator is not None:
                status, reason = "machine_code_controller_replay_verified", None
            elif gate == CANVAS_GATE and canvas is not None:
                status, reason = "generated_game_canvas_pixels_recorded", None
            elif gate == PARITY_GATE and art_parity is not None:
                status, reason = "pixel_source_parity_checked", None
            elif gate == GODOT_GATE and godot is not None:
                status, reason = "godot_gameplay_executed", None
            elif gate == BROWSER_GATE and browser is not None:
                status, reason = "javascript_gameplay_executed", None
            elif gate in NATIVE_GATES and target not in _BUILD_ADAPTERS:
                status, reason = "adapter_unavailable", "approved_native_toolchain_missing"
            else:
                status, reason = "not_qualified", (
                    "source_not_generated" if source_receipt is None
                    else "independent_runtime_or_approval_evidence_required"
                )
            gates[gate] = {"status": status, "blocker": reason}
            if status in {"artifact_integrity_checked", "binary_structure_checked", "javascript_gameplay_executed", "godot_gameplay_executed",
                          "pixel_source_parity_checked", "generated_game_canvas_pixels_recorded",
                          "machine_code_controller_replay_verified"}:
                passed += 1
        by_target.append({
            "target": target,
            "source_receipt_digest": (
                source_receipt["receipt_digest"] if source_receipt else None
            ),
            "cross_engine_pixel_parity_digest": (
                art_parity["receipt_digest"] if art_parity else None
            ),
            "generated_canvas_evidence_digest": (
                canvas["capture_digest"] if canvas else None
            ),
            "native_binary_evidence_digest": (
                binary["evidence_digest"] if binary else None
            ),
            "real_emulator_evidence_digest": (
                emulator["evidence_digest"] if emulator else None
            ),
            "browser_javascript_evidence_digest": (
                browser["evidence_digest"] if browser else None
            ),
            "godot_headless_evidence_digest": (
                godot["evidence_digest"] if godot else None
            ),
            "gates": gates,
            "release_ready": False,
            "dragon_auto_training_approved": False,
        })
    count = len(order.targets) * len(GATES)
    body = {
        "schema": SCHEMA,
        "campaign_identity": campaign["identity"],
        "project_id": order.project_id,
        "total_targets": len(order.targets),
        "targets_with_exact_source": campaign["targets_with_verified_source"],
        "native_rom_machine_code_playthroughs_verified": sum(
            row["real_emulator_evidence_digest"] is not None for row in by_target
        ),
        "native_roms_structurally_verified": sum(
            row["native_binary_evidence_digest"] is not None for row in by_target
        ),
        "generated_game_canvas_captures_verified": sum(
            row["generated_canvas_evidence_digest"] is not None for row in by_target
        ),
        "godot_headless_playthroughs_verified": sum(
            row["godot_headless_evidence_digest"] is not None for row in by_target
        ),
        "browser_javascript_playthroughs_verified": sum(
            row["browser_javascript_evidence_digest"] is not None for row in by_target
        ),
        "checked_gates": passed,
        "total_gates": count,
        "evidence_gate_coverage_percent": round(100 * passed / count, 2),
        "release_qualification_percent": 0,
        "all_targets_release_ready": False,
        "rights_approval_inferred": False,
        "dragon_training_or_weight_promotion_performed": False,
        "targets": by_target,
    }
    return {**body, "report_digest": canonical_digest(body)}



def inspect_production_assurance(order: CampaignOrder, root: str | Path) -> dict:
    """Read canonical source and platform qualifications under one campaign lock."""
    with campaign_lock(root):
        return _inspect_production_assurance_unlocked(order, root)


__all__ = [
    "StudioAssuranceError", "GATES", "qualify_campaign_target",
    "qualify_campaign_browser", "qualify_campaign_godot",
    "qualify_campaign_canvas", "qualify_campaign_emulator",
    "inspect_production_assurance",
]
