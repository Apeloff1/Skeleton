# ROM and libretro core expansion (2026-10-15)

The canonical emulator system is `skeleton/jeeves/game_emulator_catalog.py`, the isolated host/worker and the explicit Linux operator installer. This pass expands **build recipes, not installed binaries**. No ROMs, commercial system firmware, emulator binaries or proprietary keys are fetched, bundled or offered by an API.

## Exact build scope

The six default bootstrap recipes remain unchanged. The source-pinned recipe catalog now has **45** core entries. Ten newly scripted cores: `a5200`, `mupen64plus_next`, `nestopia`, `mesen`, `vba_next`, `fmsx`, `bluemsx`, `px68k`, `vice_x64`, `vice_x64sc`. Two were previously identified in the expansion contract but missing from the installer; eight add previously unbuilt recipe families or variants. All source revisions are exact SHA-1 commit pins; licenses are retained with installed source identities. Added ROM suffix hints do **not** bypass existing structural parsing, content hash checks, archive extraction bounds or worker-level libretro extension validation.

## Local operator commands

Inspect recipes without side effects:

```sh
python scripts/install_game_emulator_cores.py --list-recipes
python scripts/install_game_emulator_cores.py --list-recipes --core nestopia --core mesen
```

Build and register specific cores from pinned public source on a suitably equipped **Linux** host:

```sh
python scripts/install_game_emulator_cores.py \
  --source-root /absolute/private/core-sources \
  --install-root /absolute/private/emulators \
  --fetch-sources --core nestopia --core mesen --core vba_next
```

To attempt every recipe explicitly, with bounded jobs and per-core failure receipts:

```sh
python scripts/install_game_emulator_cores.py \
  --source-root /absolute/private/core-sources \
  --install-root /absolute/private/emulators \
  --fetch-sources --all-cores --continue-on-error --jobs 2
```

The all-core command is **not** invoked by the application or CI. It returns exit code 2 if any core fails, even if other cores build successfully. The installer does not fetch operating-system packages, redistributable BIOS/ROM content, third-party keys or extra dependencies beyond the explicit pinned source. Larger cores may require operator-installed build prerequisites. Runtime enabling uses `SKL_GAME_EMULATOR_REGISTRY=/absolute/private/emulators/cores.json` in the **server** process, not the frontend.

## Readiness and authority

| Core(s) | Target scope | Admission constraint |
| --- | --- | --- |
| Nestopia, Mesen | NES cartridges | No Famicom Disk System firmware or disk support enabled by these recipes |
| VBA-Next | GBA-family cartridges | No physical-console/accessory or accuracy guarantee |
| a5200 | Atari 5200 | Requires operator-owned `5200.rom`, missing file defers approval |
| PX68k | Sharp X68000 | Requires operator-owned `iplrom.dat` and `cgrom.dat` |
| fMSX | MSX1/MSX2 | Candidate until firmware requirements are inspected and qualified |
| blueMSX | MSX family | Candidate until copied upstream C-BIOS assets and system-directory resolution are qualified |
| VICE x64/x64sc | Commodore 64 | Candidates until original system ROMs have been legitimately installed and qualified |
| Mupen64Plus-Next | Nintendo 64 | Candidate: host software-renderer/headless compatibility is not qualified |

An `approved:false` registry record is intentionally *not* a working emulator. No installation or execution was performed by this source-only commit. Existing bubblewrap and native byte/hash checks remain required. ROM rights and upstream core licensing remain the operator's responsibility. Do not classify compatibility as verified until a separate runtime evidence receipt has been obtained.

## Remaining closure obligations

Validate the pinned sources, compiler/toolchain requirements, output names and retained licenses on the target architecture; inspect copied firmware identities; prove native ABI, sandboxed software framebuffer, reset/run/snapshot/restore/audio/input and correct controller behavior per core; confirm exact ROM/disc source admission with rights-audited homebrew; record test and environment receipts. Migrate any core from candidate to approved **only** following that review. Platform families with no public-compatible libretro implementation remain explicitly unavailable and must not fall back to reference simulation.
