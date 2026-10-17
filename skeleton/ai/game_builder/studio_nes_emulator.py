"""Optional actual NES 6502/PPU/controller playthrough through FCEUX Lua.

No fake CPU simulator: an installed FCEUX runs the real compiled NROM ROM.
An immutable ld65 VICE label file supplies the *actual* zero-page locations.
The Lua adapter injects the reference D-pad sequence, reads 6502 RAM via
memory.readbyte, and snapshots a real emulated NES framebuffer. No live GUI
desktop, user keystrokes, other applications, or third-party ROMs are captured.
FCEUX builds/CLI vary; an incompatible/missing binary fails closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile

from .contracts import canonical_digest
from .studio_build_qualification import _header, _regular, parse_nes_labels
from .studio_runtime_qualification import _inputs

SCHEMA = "skeleton.game_builder.nes_cpu_ppu_playthrough.v1"
_ACTIONS = frozenset(("up", "down", "left", "right"))
_OUTPUT = re.compile(r"NES_REPLAY_V1 ([0-9]+) ([0-9]+) ([0-9]+) ([0-9]+) ([0-9]+) ([0-9]+) ([0-9]+) ([0-9]+) ([0-9]+) ([0-9]+)\Z")
_FIELDS = ("Level", "PlayerX", "PlayerY", "Health", "Score",
           "GemsRemaining", "GameWon", "GameLost")


class NativeNESEmulationError(ValueError):
    """Native NROM input, execution or assurance claim cannot be qualified."""


@dataclass(frozen=True, slots=True)
class NESReplayResult:
    rom_sha256: str
    symbols_sha256: str
    world_digest: str
    proof_sha256: str
    emulator_available: bool
    emulator_executed: bool
    cpu_input_replay_executed: bool
    machine_code_victory: bool
    frame_count: int
    action_count: int
    ppu_frame_sha256: str | None
    cpu_state: dict | None
    blocker: str | None
    receipt_digest: str

    def as_receipt(self) -> dict:
        body = {
            "schema": SCHEMA, "target": "nintendo_famicom",
            "rom_sha256": self.rom_sha256,
            "symbols_sha256": self.symbols_sha256,
            "world_digest": self.world_digest,
            "proof_sha256": self.proof_sha256,
            "emulator_available": self.emulator_available,
            "emulator_executed": self.emulator_executed,
            "cpu_input_replay_executed": self.cpu_input_replay_executed,
            "machine_code_victory": self.machine_code_victory,
            "frame_count": self.frame_count, "action_count": self.action_count,
            "ppu_frame_sha256": self.ppu_frame_sha256,
            "cpu_state": self.cpu_state,
            "blocker": self.blocker,
            "physical_controller_verified": False,
            "physical_console_verified": False,
            "audio_hardware_verified": False,
            "model_weights_changed": False,
            "release_approved": False,
        }
        if canonical_digest(body) != self.receipt_digest:
            raise NativeNESEmulationError("NES emulator evidence was modified")
        return {**body, "receipt_digest": self.receipt_digest}


def _receipt(rom: str, symbols: str, world: str, proof: str, *,
             available: bool, executed: bool = False, replay: bool = False,
             victory: bool = False, frames: int = 0, actions: int = 0,
             image: str | None = None, state: dict | None = None,
             blocker: str | None = None) -> NESReplayResult:
    body = {
        "schema": SCHEMA, "target": "nintendo_famicom",
        "rom_sha256": rom, "symbols_sha256": symbols,
        "world_digest": world, "proof_sha256": proof,
        "emulator_available": available, "emulator_executed": executed,
        "cpu_input_replay_executed": replay, "machine_code_victory": victory,
        "frame_count": frames, "action_count": actions, "ppu_frame_sha256": image,
        "cpu_state": state, "blocker": blocker,
        "physical_controller_verified": False,
        "physical_console_verified": False,
        "audio_hardware_verified": False,
        "model_weights_changed": False,
        "release_approved": False,
    }
    return NESReplayResult(
        rom, symbols, world, proof, available, executed, replay, victory,
        frames, actions, image, state, blocker, canonical_digest(body),
    )


def _script(actions: list[str], labels: dict[str, int],
            *, max_frames: int) -> str:
    """Construct fixed-script Lua with only validated ASCII control literals."""
    if (not 1 <= len(actions) <= 20_000
            or any(type(a) is not str or a not in _ACTIONS for a in actions)
            or set(labels) != set(_FIELDS)
            or type(max_frames) is not int or not 20 <= max_frames <= 260_000):
        raise NativeNESEmulationError("bounded, exact canonical input data required")
    names = ",".join('"' + action + '"' for action in actions)
    refs = ",".join(f"{name}=0x{labels[name]:02X}" for name in _FIELDS)
    # The actual FCEUX memory/joypad/framebuffer APIs are documented in
    # https://fceux.com/web/help/LuaFunctionsList.html.
    return """
local actions = {""" + names + """}
local ram = {""" + refs + """}
local total = 0
local maximum = """ + str(max_frames) + """
local function advance(count)
  for n=1,count do
    total=total+1
    if total > maximum then return false end
    emu.frameadvance()
  end
  return true
end
local ok = advance(120)
if ok then
  for _, button in ipairs(actions) do
    joypad.set(1, {[button]=true})
    ok = advance(3)
    joypad.set(1, {[button]=false})
    if not ok then break end
    ok = advance(12)
    if not ok then break end
  end
end
joypad.set(1, {up=false,down=false,left=false,right=false})
if ok then
  local outcome = io.open("replay-result.txt", "wb")
  if outcome ~= nil then
    local values = {
      total, #actions,
      memory.readbyte(ram.Level), memory.readbyte(ram.PlayerX),
      memory.readbyte(ram.PlayerY), memory.readbyte(ram.Health),
      memory.readbyte(ram.Score), memory.readbyte(ram.GemsRemaining),
      memory.readbyte(ram.GameWon), memory.readbyte(ram.GameLost)
    }
    outcome:write("NES_REPLAY_V1 " .. table.concat(values, " "))
    outcome:close()
  end
  if gui ~= nil and type(gui.gdscreenshot) == "function" then
    local frame = gui.gdscreenshot(true)
    if frame ~= nil and #frame > 100 and #frame < 2000000 then
      local visual = io.open("framebuffer.gd", "wb")
      if visual ~= nil then
        visual:write(frame)
        visual:close()
      end
    end
  end
end
if emu ~= nil and type(emu.exit) == "function" then
  emu.exit()
end
"""


def qualify_nes_cpu_ppu(
    qualification: str | Path, *, engine_source: str | Path,
    authorized: bool, execute: bool, timeout_seconds: int = 90,
    max_frames: int = 260_000,
) -> NESReplayResult:
    if authorized is not True:
        raise PermissionError("actual NES CPU emulation requires operator authorization")
    if type(execute) is not bool:
        raise NativeNESEmulationError("explicit NES emulator execution flag required")
    if (type(timeout_seconds) is not int or not 5 <= timeout_seconds <= 120
            or type(max_frames) is not int or not 20 <= max_frames <= 260_000):
        raise NativeNESEmulationError("NES native runtime budget must be finite")
    root = Path(qualification)
    if root.is_symlink() or not root.is_dir():
        raise NativeNESEmulationError("valid native qualification root required")
    try:
        rom = _regular(root / "qualified.rom", 8 * 1024 * 1024)
        sym = _regular(root / "qualified.sym", 128_000)
        _header("nes", rom)
        labels = parse_nes_labels(sym)
        _, proof, world = _inputs(Path(engine_source))
        trace = json.loads(proof)
    except (OSError, UnicodeError, ValueError) as exc:
        raise NativeNESEmulationError("native NES cartridge/symbols/replay failed preflight") from exc
    actions = trace.get("actions")
    expected = trace.get("final_state")
    if (type(actions) is not list or not 1 <= len(actions) <= 20_000
            or any(type(a) is not str or a not in _ACTIONS for a in actions)
            or type(expected) is not dict or expected.get("status") != "won"
            or any(type(expected.get(k)) is not int for k in (
                "x", "y", "score", "health", "level_index"
            ))):
        raise NativeNESEmulationError("canonical replay lacks bounded winning action trace")
    emulator = shutil.which("fceux")
    romhash, symhash, proofhash = (
        sha256(rom).hexdigest(), sha256(sym).hexdigest(), sha256(proof).hexdigest(),
    )
    if emulator is None:
        return _receipt(romhash, symhash, world, proofhash,
                        available=False, blocker="fceux_not_installed")
    if not execute:
        return _receipt(romhash, symhash, world, proofhash,
                        available=True, blocker="nes_cpu_execution_not_authorized")
    with tempfile.TemporaryDirectory(prefix="skeleton-fceux-original-") as temp:
        scratch = Path(temp)
        cartridge = scratch / "original.nes"
        cartridge.write_bytes(rom)
        script = scratch / "playthrough.lua"
        script.write_text(_script(actions, labels, max_frames=max_frames), encoding="ascii")
        log = scratch / "emulator.log"
        try:
            with log.open("wb") as output:
                result = subprocess.run(
                    [emulator, "--no-config", "1", "--nogui", "1",
                     "--loadlua", str(script), str(cartridge)],
                    cwd=scratch, shell=False, check=False, timeout=timeout_seconds,
                    stdout=output, stderr=subprocess.STDOUT,
                    env={"PATH": os.defpath, "HOME": temp,
                         "XDG_CONFIG_HOME": temp, "XDG_DATA_HOME": temp,
                         "LC_ALL": "C",
                         **({"DISPLAY": os.environ["DISPLAY"]}
                            if "DISPLAY" in os.environ else {})},
                )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return _receipt(romhash, symhash, world, proofhash,
                            available=True, executed=True,
                            blocker="nes_emulator_execution_failed:" + type(exc).__name__)
        if result.returncode != 0 or log.stat().st_size > 128_000:
            return _receipt(romhash, symhash, world, proofhash,
                            available=True, executed=True,
                            blocker="nes_emulator_process_failed")
        file = scratch / "replay-result.txt"
        try:
            report = _regular(file, 400).decode("ascii").strip()
        except (OSError, ValueError, UnicodeError):
            return _receipt(romhash, symhash, world, proofhash,
                            available=True, executed=True,
                            blocker="nes_emulator_did_not_write_cpu_evidence")
        match = _OUTPUT.fullmatch(report)
        if match is None:
            return _receipt(romhash, symhash, world, proofhash,
                            available=True, executed=True,
                            blocker="nes_cpu_evidence_format_invalid")
        numbers = tuple(int(x) for x in match.groups())
        frames, count = numbers[:2]
        state = dict(zip(_FIELDS, numbers[2:]))
        if (frames > max_frames or frames < count * 15 + 120
                or count != len(actions) or any(not 0 <= v <= 255 for v in state.values())):
            return _receipt(romhash, symhash, world, proofhash,
                            available=True, executed=True,
                            frames=frames, actions=count,
                            blocker="nes_cpu_trace_outside_expected_frame_budget")
        image = None
        file = scratch / "framebuffer.gd"
        if file.exists():
            try:
                image = sha256(_regular(file, 2_000_000)).hexdigest()
            except (OSError, ValueError):
                return _receipt(romhash, symhash, world, proofhash,
                                available=True, executed=True,
                                blocker="nes_ppu_framebuffer_invalid")
        # Complete CPU/PPU evidence requires a genuine emulator-produced
        # framebuffer, never just the RAM victory flag or scripted input.
        if image is None:
            return _receipt(
                romhash, symhash, world, proofhash,
                available=True, executed=True, replay=True,
                frames=frames, actions=count, state=state,
                blocker="nes_emulated_ppu_framebuffer_unavailable",
            )
        # NROM source increments Level after entering the final goal.
        victory = (
            state["GameWon"] == 1 and state["GameLost"] == 0
            and state["GemsRemaining"] == 0
            and state["PlayerX"] == expected["x"]
            and state["PlayerY"] == expected["y"]
            and state["Level"] == expected["level_index"] + 1
            and state["Health"] == expected["health"]
            and state["Score"] == expected["score"]
        )
        return _receipt(
            romhash, symhash, world, proofhash,
            available=True, executed=True, replay=True, victory=victory,
            frames=frames, actions=count, image=image, state=state,
            blocker=None if victory else "nes_machine_code_diverged_from_reference_replay",
        )


__all__ = [
    "NativeNESEmulationError", "NESReplayResult",
    "qualify_nes_cpu_ppu", "parse_nes_labels",
]
