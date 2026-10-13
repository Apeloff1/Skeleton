"""Conservative homebrew source-compatibility revisions, not new engines.

Only match the same ISA, cartridge type and native execution mode.
The returned project is branded for its destination, carries original
parent-source custody, and never claims that a parent binary ran on
the revision. Firmware, accessory and input caveats remain explicit.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict,replace
from hashlib import sha256
import json

@dataclass(frozen=True)
class CompatibleRevision:
    target:str
    parent:str
    runtime_mode:str
    output:str
    assumption:str
    required_test:str

REVISIONS=(
 CompatibleRevision("game_boy_pocket","game_boy","DMG-compatible SM83 ROM","gb",
  "Pocket runs monochrome DMG cartridges; LCD/motion quality differs",
  "RGBDS build plus Pocket display, input and audio replay"),
 CompatibleRevision("game_boy_light","game_boy","DMG-compatible SM83 ROM","gb",
  "Game Boy Light uses DMG software; backlight and screen response differ",
  "DMG emulator plus Game Boy Light hardware video/audio"),
 CompatibleRevision("game_boy_micro","game_boy_advance","GBA native ARM7 cartridge","gba",
  "Micro is GBA-compatible but lacks older DMG/CGB cartridge support",
  "devkitARM compiler plus Micro input/audio and LCD"),
 CompatibleRevision("game_boy_player","game_boy_advance","GBA ARM7 game in Game Boy Player","gba",
  "Game Boy Player runs GBA cartridge in GameCube peripheral with controller",
  "GBA emulator plus GBP controller, timing and TV output"),
 CompatibleRevision("psp_go","psp","PSP Allegrex homebrew EBOOT","pbp",
  "PSP Go storage/firmware loading differs from UMD PSP models",
  "PSPSDK build plus PSP Go firmware-mode execution"),
 CompatibleRevision("psp_street","psp","PSP Allegrex homebrew EBOOT","pbp",
  "PSP Street lacks wireless networking; gameplay uses no networking",
  "PSPSDK build plus PSP Street controller and display"),
 CompatibleRevision("nintendo_switch_lite","nintendo_switch","libnx ARM64 NRO handheld layout","nro",
  "Switch Lite runs the same documented libnx homebrew ABI with integrated handheld input; Joy-Con detachment is unavailable",
  "devkitA64 build plus Switch Lite input, handheld display and firmware-mode execution"),
 CompatibleRevision("nintendo_switch_oled","nintendo_switch","libnx ARM64 NRO handheld/docked mode","nro",
  "OLED revision uses the supported Switch homebrew ISA; dock resolution, screen color and controllers need separate checks",
  "devkitA64 build plus Switch OLED dock/handheld controller and visual replay"),
 CompatibleRevision("nintendo_dsi","nintendo_ds","Nintendo DS compatibility mode","nds",
  "DS homebrew runs in DS mode; DSi-only camera/RAM not claimed",
  "devkitARM libnds build plus DSi compatibility-mode replay"),
 CompatibleRevision("nintendo_2ds","nintendo_3ds","CTR ARM11 homebrew 2D display","3dsx",
  "2DS presents the 3DS game in 2D, without stereoscopic effects",
  "libctru/citro2d build plus 2DS touch and display"),
 CompatibleRevision("new_nintendo_3ds","nintendo_3ds","CTR ARM11 backward-compatible mode","3dsx",
  "No enhanced New 3DS CPU speed, extra inputs or memory assumed",
  "libctru build plus New 3DS old-mode gameplay replay"),
 CompatibleRevision("atari_130xe","atari_400_800","6502 Atari 8-bit 48KiB-compatible program","xex",
  "130XE may run compatible Atari 8-bit games; extra XE banks unused",
  "cc65 Atari target XEX plus 130XE memory/keyboard"),
 CompatibleRevision("sega_mark_iii","master_system","Mark III compatible Sega VDP/Z80","sms",
  "Mark III cartridge connections and FM variants require separate review",
  "SMS compatible Z80 ROM build and Mark III controller/palette"),
 CompatibleRevision("amiga_1200","amiga_500","Kickstart-compatible 68000 Amiga Hunk","hunk",
  "A1200 68020/AGA can execute original 68000 Intuition 1.3 window source; no enhanced AGA graphics, faster CPU or CD32 pad claimed",
  "vbcc +kick13 build and A1200 keyboard/graphics.library AmigaOS emulator replay"),
 CompatibleRevision("atari_falcon","atari_st","Atari TOS/GEMDOS 68000 compatible executable","tos",
  "Falcon 68030 supports TOS user-mode GEMDOS; does not prove VIDEL/DSP sound, enhanced display or 68030-specific performance",
  "m68k-atari-mint-gcc build plus Falcon TOS keyboard and 68000 code compatibility emulator replay"),
)
COMPATIBILITY={r.target:r for r in REVISIONS}
assert len(COMPATIBILITY)==len(REVISIONS)
assert len({r.parent for r in REVISIONS})>=6
assert all(r.target!=r.parent for r in REVISIONS)

def revision_project(*,target_id:str,title:str,style:str,candidate_id:str,
                     mechanics:tuple,authorized:bool,design,
                     renderer):
    if target_id not in COMPATIBILITY:
        raise ValueError("target not an approved native compatibility variant")
    if not authorized:
        raise PermissionError("native compatibility source requires authorization")
    revision=COMPATIBILITY[target_id]
    from .dragon_native_targets import CATALOG
    from .dragon_native_projects import NativeProject,digest
    expected=CATALOG[target_id]
    parent=CATALOG[revision.parent]
    if expected.output!=parent.output or expected.output!=revision.output:
        raise ValueError("hardware output/ABI mismatch; reject misleading target")
    if design is not None and (design.target!=target_id or
                               design.title!=title or design.genre!=style):
        raise ValueError("incompatible user game design target")
    base_design=replace(design,target=revision.parent) if design is not None else None
    game=renderer(title=title,target_id=revision.parent,style=style,
                  candidate_id=candidate_id,mechanics=mechanics,
                  authorized=True,design=base_design)
    files=dict(game.files)
    # Preserve the exact parent budget under its true hardware identity;
    # do not transplant that memory proof to a different device.
    if "dragon-hardware-budget.json" in files:
        files["dragon-parent-hardware-budget.json"]=files.pop("dragon-hardware-budget.json")
    if "dragon-game-design.json" in files and design is not None:
        from .dragon_game_design import design_manifest
        files["dragon-game-design.json"]=json.dumps(
            design_manifest(design),sort_keys=True,indent=2)+"\n"
    receipt={"schema":"skeleton.ai.dragon.compatible_revision.v1",
         **asdict(revision),
         "source_parent_fingerprint":game.digest,
         "target_compiler_verified":False,
         "target_emulator_verified":False,
         "target_hardware_verified":False,
         "native_source_reused_without_binary_substitution":True}
    files["dragon-compatible-revision.json"]=json.dumps(
        receipt,sort_keys=True,indent=2)+"\n"
    metadata=json.loads(files["dragon-native-manifest.json"])
    if metadata.get("target")!=revision.parent:
        raise ValueError("native base source target receipt mismatch")
    metadata["target"]=target_id
    metadata["source_parent"]=revision.parent
    metadata["compatible_runtime_mode"]=revision.runtime_mode
    metadata["target_compiler_verified"]=False
    files["dragon-native-manifest.json"]=json.dumps(
        metadata,sort_keys=True,indent=2)+"\n"
    files["README.compatibility.md"]=(
        "# Original "+target_id+" native compatibility project\n\n"
        "Compatible parent: "+revision.parent+
        ". Native mode: "+revision.runtime_mode+".\n"
        "Assumption: "+revision.assumption+".\n"
        "Required verification: "+revision.required_test+".\n"
        "This is SOURCE custody for a compatible ABI, not a separately "
        "verified executable, emulator session, or physical device test. "
        "Never claim commercial cartridge/SDK authorization from this.\n")
    finger=digest(files)
    return NativeProject(
        digest([candidate_id,target_id,style,finger]),
        target_id,style,game.title,"source_generated",
        expected.toolchain,expected.output,files,finger,
        game.supported_mechanics,game.deferred_mechanics)
