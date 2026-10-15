# ROM emulator integration — third expansion (2026-10-15)

## Scope and verified boundary

Eight further source-pinned Linux libretro recipes are integrated in the **existing** operator installer and canonical Jeeves hardware/core registry. Source recipes now total **67** (prior 59, plus 8). All new cores are marked `candidate_only`; **zero new compiled or gameplay-verified emulators** are claimed. The **169** platform/machine rows remain a *hardware target* inventory, not verified emulator binaries. The canonical compatibility mirror receives the identical data additions. Nothing here downloads game ROMs, BIOS files, keys, licensed SDKs or commercial assets.

| Core | Target family | Inspected upstream build | Qualification gate |
| --- | --- | --- | --- |
| Gearboy | GB / GBC / pocket / light | `platforms/libretro/Makefile` | Model, boot modes, link peripherals |
| Gearsystem | Master System / Mark III / SG-1000 / Game Gear | `platforms/libretro/Makefile` | Mapper, region, timing and firmware |
| gpSP | GBA / Micro / Player | `Makefile`, `HAVE_DYNAREC=0` | Interpreter and firmware review |
| Beetle PSX software (`mednafen_psx`) | PS1 | `Makefile`, all graphics acceleration disabled | Operator BIOS, disc/video/audio |
| Snes9x 2005 | SNES | `Makefile` | CPU/audio timing and enhancement chips |
| Snes9x 2010 | SNES | `Makefile.libretro` | Accuracy, co-processors and peripherals |
| Supafaust | SNES | `Makefile` | Special cartridge and timing traces |
| BlastEm | Genesis / Mega Drive | `Makefile.libretro core` | CPU, audio, regional mappers |

Revisions are frozen to the exact 40-character upstream commits in `scripts/install_game_emulator_cores.py` and mirrored in `machine/ai_game_emulator_catalog.json`. Those identifiers and build entry points were inspected against upstream repositories; actual reproducibility **must be established by compiling on the target Linux host**. Every installed shared library still passes the existing ELF/libretro-symbol inspection and SHA-256 immutable artifact admission before a deferred registry record is written.

## Architecture, safety and production learning L00–L13

- **L00–L02:** Existing owner: `skeleton/jeeves/game_emulator_catalog.py`, existing compatibility mirror, existing installer and pinned machine contract. No new service, runtime root or provider boundary.
- **L03–L04:** Exact source pins, bounded build commands and candidate-only installation are deliberately separate from runtime approval. Native load remains guarded by the worker and exact registry digest.
- **L05–L06:** Existing bounded content, multi-file dependency, path-traversal, zip safety and firmware rules remain in force. Extension hints neither activate a core nor authorize native execution; worker confirms live upstream extensions.
- **L07–L08:** Retain per-core compilation log, origin/ref identity, immutable .so SHA, source tree and license receipts; abort on source/ABI/admission mismatch. Never substitute a reference scene for emulation.
- **L09:** Operator bounds: `--jobs 1..8`, command timeout `30..3600` seconds; gpSP dynarec and Beetle hardware renderers explicitly disabled. Existing sandbox CPU/memory/IO policies still apply.
- **L10:** Neither a native build nor ROM trace, CI test, install or visual verification was performed by this update. Before promotion require Linux ABI compilation, program-owned homebrew images, controller/frame/audio, reset/save-state, deterministic replay, region/disk, firmware and security traces.
- **L11–L12:** Explicit `--core` selection prevents default bulk acquisition; all eight are deferred even if they compile. Roll back by reverting this single commit and revoking any operator approvals of changed candidates.
- **L13:** No measured weight/parameter gain and no production model training. Training admissions require reference-digested ROM rights, real core execution evidence, learning-outcome receipts, evaluation and separate promotion approval.

## Operator build command (only when a qualified Linux build host exists)

```bash
python3 scripts/install_game_emulator_cores.py --list-cores
python3 scripts/install_game_emulator_cores.py --source-root /srv/skeleton-emulator-sources --install-root /srv/skeleton-emulators --fetch-sources --core gearboy --core gearsystem --jobs 2
```

The installer does not execute games; building BlastEm uses the upstream `core` target rather than silently accepting a missing library. The `--profile starter` baseline is unchanged; `--profile broad` excludes these deferred candidates. Inspect licenses independently before redistribution or commercial deployment.

## Remaining gap

67 declared recipe IDs **is not 67 working emulators** and does not mean 67 of 169 machines are covered. Remaining work includes operator builds, controlled legal firmware, source and native runtime validation, mapper/peripheral/disk support, stable saves, real emulator evidence and per-target training quality before coverage percentages can be stated.
