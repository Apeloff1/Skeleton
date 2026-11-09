# ROM emulator integration — second expansion (2026-10-15)

## Scope and evidence

This changes the **operator build recipe registry**, not the count of successfully emulated platforms. The current baseline was 51 declared pinned libretro recipes. Eight additional exact upstream revisions and Linux libretro build entry points are now registered: **59 declared recipes total**. Every added target was already recognized by the canonical core-to-hardware registry. This pass does not compile a native core, load any ROM, run end-to-end validation, approve restricted firmware, or qualify actual gameplay.

These source repositories, full pinned commits, target artifacts, and license paths were inspected against upstream GitHub trees before authoring the recipes. Build behavior remains provisional until compilation on the production Linux ABI. These recipes do not bring 169 hardware rows to working status. No commercial ROMs, BIOS, encryption keys, licensed SDKs or proprietary game assets are distributed.

| Core | Hardware targets | Build path | Default admission |
| --- | --- | --- | --- |
| bsnes | SNES | upstream root Makefile | Buildable candidate, operator must install |
| PUAE | Amiga 500/1200/CD32 | root Makefile | Deferred: lawful Kickstart, drives, storage |
| NP2kai | NEC PC-9801 | sdl/Makefile.libretro | Deferred: machine fonts/firmware and input |
| DOSBox SVN | DOS 8086/CGA/EGA/VGA/VESA; Win16 | libretro/Makefile.libretro | Deferred: executable selection and filesystem |
| Yabause | Saturn | yabause/src/libretro/Makefile | Deferred: BIOS/HLE, disc control and rendering |
| Hatari | Atari ST/Falcon | CMake ENABLE_LIBRETRO | Deferred: lawful TOS and specialized machine modes |
| SwanStation | PlayStation 1 | root Makefile.libretro | Deferred: firmware and graphics |
| Mupen64Plus-Next | Nintendo 64 | root Makefile | Deferred: hardware graphics context |

### Production boundary L00–L13

- **L00–L02 — ownership and contract:** Remain within `scripts/install_game_emulator_cores.py`, the canonical `skeleton/jeeves/game_emulator_catalog.py` owner, its required compatibility mirror, and the pinned installation machine contract. No new runtime or service root.
- **L03–L04 — admission and execution:** A source pin is only a build instruction. Operator installation must check Git commit, compilation and exported libretro ABI. Explicit approval, current exact registry SHA and bubblewrap isolation are separate from a functioning game. The candidate-only recipes are deferred even after successful compilation.
- **L05–L06 — data/security:** Existing bounded filename, content hash, archive and multi-file manifest rules remain mandatory. Only approved operator firmware is eligible. No arbitrary client paths, network acquisition at runtime or in-worker firmware downloads.
- **L07–L08 — recovery and logging:** Build failure must preserve the private per-core log and abort the batch. No incompatible core is substituted, and no reference scene is labeled emulation. Compiled artifacts get immutable content hashes, source receipts and precise scope.
- **L09 — economics:** `--jobs` and install timeouts bound operator build parallelism; native playback retains per-worker limits. Source trees are potentially very large and should be budgeted separately per core.
- **L10 — verification:** No executable builds or emulator/ROM runs were performed in this change. Qualification requires clean Linux toolchain builds, ELF symbol scans, BIOS audits, input/video/audio checks, save-state and disc-control exercises, long deterministic reference traces, and legal homebrew acceptance ROMs.
- **L11–L12 — deployment and rollback:** Install via the existing operator CLI, opt in to each core with `--core`, and activate through the private registry. Revoke an approval or restore the earlier immutable manifest to roll back. Keep candidate approvals disabled until host prerequisites are validated.
- **L13 — release/learning gate:** Production-model training and claims of successful emulation require exact core/ROM/source/firmware identities plus verified game outcomes; a pinned recipe alone is insufficient.

### Operator commands

```bash
python3 scripts/install_game_emulator_cores.py --list-cores

# Explicit one-core source acquisition and compile. This does not run games:
python3 scripts/install_game_emulator_cores.py \
  --source-root /srv/skeleton-emulator-sources \
  --install-root /srv/skeleton-emulators \
  --fetch-sources --core bsnes --jobs 2
```

For controlled rollouts, use repeated `--core` to select specific recipes; the default starter profile remains unchanged. `--profile all` includes blocked candidates, but will stop at the first build/admission failure. Do not use an all-profile bulk install as proof of broad readiness.

### Remaining work toward 169 hardware identities

Count canonical hardware rows, then enumerate three separate sets: (1) upstream source recipes, (2) compiled locally installed approved binaries, and (3) gameplay-qualified hardware targets. Target families with no safe open libretro adapter remain unsupported. Highest-priority capability gaps are native software renderer coverage, disk swapping, firmware-region/variant manifests, specialized keyboard/mouse/touch inputs, durable battery saves and per-game reference-trace qualification.
