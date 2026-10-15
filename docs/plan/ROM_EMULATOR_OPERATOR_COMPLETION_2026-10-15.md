# ROM and libretro core operator admission — reconciled 2026-10-15

This reconciles PR #3933 with the later canonical mainline. The early PR described 49 pinned recipes; the current canonical source manifests already enumerate **83 exact source-pinned recipes**, including all fourteen proposed IDs, so the older 49-item catalog must not overwrite main. These are source recipes, **not installed, booted or verified emulators**.

## Explicit Linux operator actions

Read-only source inventory:

```sh
python scripts/install_game_emulator_cores.py --list-cores
python scripts/install_game_emulator_cores.py --coverage-matrix
python scripts/install_game_emulator_cores.py --validate-recipes
```

Operator-pinned bulk attempt with per-core failure receipts:

```sh
python scripts/install_game_emulator_cores.py \
  --source-root /absolute/private/sources \
  --install-root /absolute/private/cores \
  --profile all --fetch-sources --continue-on-error --jobs 2
```

The installer continues to the next selected core only when `--continue-on-error` is explicit. It records `selected_count`, `installed_count`, `failed_count`, per-core error type/message and the resolved registry if present; any failure exits **2**, including an entirely failed batch. Without that flag, the first failure retains the former fail-fast behavior. No automatic install, ROM, firmware acquisition, secret inclusion, runtime approval or model training occurs. Runtime approval remains controlled by validated core/firmware identity and sandbox policy. Operator must independently test actual video, audio, controller, disc/save behaviors and lawful homebrew content before declaring compatibility.

The earlier `--list-recipes` request is fulfilled by the existing `--list-cores`, and `--all-cores` by existing `--profile all`; introducing duplicate, divergent switches is avoided. The exact external native build jobs and full game playthroughs remain unverified by this source reconciliation.
