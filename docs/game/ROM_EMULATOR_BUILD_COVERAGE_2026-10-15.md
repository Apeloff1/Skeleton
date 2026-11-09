# ROM/emulator build coverage — 2026-10-15

## Scope and trust boundary

**This change adds real, source-pinned build recipes, not prebuilt cores.** The registry has 51 named Linux libretro build recipes: 35 pre-existing and 16 added in this pass. Neither this commit nor its source manifests establish that those 51 libraries were compiled, installed, loaded, exercised with ROMs, or certified against original hardware. Historic build claims in the machine manifest refer to a previous environment and are not fresh verification.

The canonical hardware catalog intentionally contains additional systems without a runnable backend. A catalog row, supported ROM suffix, successful compiler exit, and operator approval are distinct from successful gameplay. Unsupported hardware and missing BIOS/key material continue to fail closed. No downloaded games, proprietary firmware, encryption keys, DRM bypass or bundled commercial ROMs are added.

## New pinned source recipes

| Cores | Declared hardware targets | Admission |
| --- | --- | --- |
| Nestopia, Mesen | NES cartridges | Software-core recipe; FDS is outside mapped targets |
| SameBoy | DMG, Pocket, Light, Color Game Boy | Software-core recipe |
| VBA Next | Game Boy Advance, Micro, Player | Software-core recipe |
| blueMSX | MSX1 and MSX2 | Deferred until pinned public C-BIOS directory setup works in isolated runtime |
| fMSX | MSX1 and MSX2 | Deferred for operator firmware and runtime layout |
| VICE x64, x64sc | Commodore 64 | Deferred for lawful Commodore/drive ROMs and qualified runtime |
| VICE x128, xvic, xplus4, xpet | C128, VIC20, Plus/4, PET | Deferred for lawful machine/drive ROMs and qualified runtime |
| PX68k | Sharp X68000 | Deferred for operator firmware and disk handling |
| Quasi88 | NEC PC-8801 | Deferred for operator firmware and disk handling |
| Beetle Saturn (software) | Sega Saturn | Deferred for operator firmware and disc control |
| Atari 5200 | Atari 5200 | Deferred for operator firmware and runtime lookup |

Every new recipe carries an exact public upstream URL and full commit SHA. The handheld/legacy ROM admission hints were checked against upstream `retro_get_system_info` declarations where available and are not execution privileges. The host again checks the loaded core's live extensions, exact registry and ROM bytes.

## Operator use

List all source candidates without any download, compilation or core initialization:

```bash
python3 scripts/install_game_emulator_cores.py --list-cores
```

Install exactly one selected core after reviewing its upstream license and dependency requirements. Use absolute, private directories:

```bash
python3 scripts/install_game_emulator_cores.py \
  --source-root /srv/skeleton-emulator-sources \
  --install-root /srv/skeleton-emulators \
  --fetch-sources --core sameboy --jobs 2
```

Batch options: `--profile starter` retains the original six default core recipes, `--profile broad` selects the non-deferred recipe set, and `--profile all` also attempts the declared candidate-only recipes. Explicit repeated `--core` selections override the profile. Batch installation currently stops on the first compilation/admission error. Installed compilations are inspected as ELF shared libraries and installed by content hash; installing does not run the core or a ROM.

An operator must separately configure and expose the actual registry file to the application, for example by setting `SKL_GAME_EMULATOR_REGISTRY=/srv/skeleton-emulators/cores.json` in its private service environment. Approved entries still require the isolated Linux bubblewrap worker at execution. Readiness should be observed via the existing emulator console catalog; no host path or approval is accepted from normal API clients.

## Remaining compatibility gaps

- Compile and install the selected upstream pinned sources on the target Linux ABI; inspect actual build logs, shared libraries and dependencies. There is no evidence this change performed that work.
- Supply legitimate BIOS/assets when required and reapprove only exact scoped targets after verifying their availability; candidate-only cores cannot become ready automatically.
- Extend the native libretro host for advanced hardware rendering, disk swapping where required, specialized input, firmware variants and core-specific environments. These have not been implemented here.
- Check native load/frames/audio/snapshots and actual game outcomes on legally owned test material before making emulator compatibility or model-training claims.
- Add separate carefully audited, legally distributable solutions for currently unmapped platforms rather than treating catalog coverage as emulator availability.

Historical backend support includes a bounded native Game Boy ROM interpreter, distinct from the multi-core libretro host. This pass expands the latter; it does not convert reference scene simulation into CPU-accurate emulation, and it does not distribute any game ROM.
