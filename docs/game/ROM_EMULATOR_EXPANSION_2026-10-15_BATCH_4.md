# ROM emulator integration — fourth source-build expansion (2026-10-15)

## What is actually implemented

Extends the existing pinned operator source-build registry **67 → 75 declared recipes**. The eight new IDs are **not eight tested, compiled, installed or gameplay-qualified emulators**. These pinned upstream source revisions and Linux Makefile paths were inspected. The 169 hardware rows remain distinct from the number of source recipes and from verified execution.

| Core | Canonical hardware IDs | Upstream entry point | Admission |
| --- | --- | --- | --- |
| Snes9x 2002 | `snes` | root Makefile | Deferred; noncommercial/accuracy review |
| SMS Plus GX | `master_system`, `sega_mark_iii`, `sega_sg1000`, `game_gear` | Makefile.libretro | Deferred; model/region and third-party audio licensing |
| TGB Dual | GB/Color/Pocket/Light | root Makefile | Deferred; serial link and save consistency |
| Beetle Lynx | `lynx` | root Makefile | Deferred; rotation/input/BIOs scope |
| Meteor | `game_boy_advance`, `game_boy_micro`, `game_boy_player` | libretro/Makefile | Deferred; ARM timing and SRAM |
| MAME 2003 Plus | `neo_geo` only | root Makefile | Deferred; Neo Geo firmware, exact ROM-set, noncommercial restrictions |
| Genesis Plus GX Wide | `genesis` only | Makefile.libretro | Deferred; widescreen accuracy and cropping |
| Mesen-S | `snes` | Libretro/Makefile | Deferred; CPU/SPC700 and enhancement co-processors |

The upstream SHAs and required license files are stored in `scripts/install_game_emulator_cores.py`, mirrored into `machine/ai_game_emulator_catalog.json`. `skeleton/jeeves/game_emulator_catalog.py` and `skeleton/ai/agents/jeeves/game_emulator_catalog.py` retain identical changes in their core/hardware maps and extension hints. All eight explicitly set `candidate_only=True`. The starter and broad profiles therefore do not turn these candidates into a bulk automatic installation.

## Correctness and security work

- Special target fix: `build_target=core` for the previously added BlastEm core must be on the **build** command, not the `clean` command; clean now excludes that target.
- Arcade ZIP path: approved MAME 2003 Plus can retain an opaque native ZIP after existing bounded ZIP preflight, content hash, strict paths, member count, streaming expansion/CRC, and archive rules. The isolated worker must still validate the actual loaded libretro `block_extract` and `valid_extensions`. It cannot bypass the core registry or enable arbitrary archives for other cores.
- Every native library still requires exact source SHA, unchanged tracked checkout, host build, ELF/libretro ABI export inspection, immutable SHA-256, operator licensing, and explicit core/target approval. Missing BIOS still defers the record. ROMs, BIOS/firmware, proprietary SDKs and encryption keys are **not** provided.
- License note: MAME 2003 Plus retains classic MAME **noncommercial restrictions**. Snes9x 2002 carries older restrictive license provisions. No redistribution or commercial usage rights are inferred from source access.

## Acceptance/evidence L00–L13

- **L00–L02:** Canonical Jeeves emulator catalog owner and existing installer; no new provider, service or independent runtime.
- **L03–L04:** Pinned source-build candidate is separate from ELF admission; operator installation is separate from qualified execution or game compatibility.
- **L05–L06:** Strict authorization, descriptor/ZIP materialization and current registry guards remain fail closed; live worker ABI validation is mandatory.
- **L07–L08:** Per-core installation logs, exact upstream source/tree identity, license copy, installed artifact content hash and failure classification retained.
- **L09:** Build `--jobs` and `--timeout` remain operator bounded. Large arcade cores must not be silently acquired by default.
- **L10:** No native compilation, ROM execution, emulation tests or measured timing happened during this change. Must qualify each core with lawful homebrew samples, deterministic emulator frames/audio/input traces, savestates, BIOS policy, multi-disc/media and precise controller paths.
- **L11–L12:** Explicit opt-in via `--core`; leave deferred in operator registry; rollback by revoking core or reverting this commit. No automatic `all` profile rollout.
- **L13:** No production-model weights/parameters were trained or promoted. Training-quality claims require measured, independently reviewed trace improvements and clean source/ROM rights.

## Operator commands

```bash
python3 scripts/install_game_emulator_cores.py --list-cores
python3 scripts/install_game_emulator_cores.py --coverage-matrix

# Source fetch/build only, requires an operator-qualified Linux toolchain and source licenses
python3 scripts/install_game_emulator_cores.py \
  --source-root /srv/skeleton-emulator-sources \
  --install-root /srv/skeleton-emulators \
  --fetch-sources --core mednafen_lynx --core mesen_s --jobs 2
```

These commands are illustrative. No execution on the production host occurred in this pass.

## Hardware-mapping audit and operator recipe inspection

The canonical inventory is 47 primary + 122 supplemental hardware/OS/ABI rows = **169 identities**. Based on the canonical `_CORE_TARGET_GROUPS` declaration, **99** rows have at least one named libretro core mapping and **70** have no named mapping. Mapping is metadata, not proof that a core recipe is pinned, installed, capable of loading a ROM, or gameplay-qualified. Many of the 70 gaps represent modern phones/PCs, operating systems and restricted hardware where a ROM emulator is neither an accurate nor a licensed integration mechanism. Do not use 99/169 as a playable coverage percentage.

The preexisting read-only `--list-cores` output now additionally includes the exact library artifact, upstream license review, makefile/build directory/target, feature limits and operator build dependencies. This makes per-core rollout blockers visible before any source fetching, compilation or registry approval.
