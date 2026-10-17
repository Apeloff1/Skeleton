# All admitted local ROMs — audited Jeeves/Dragon training fleet

**Status:** implemented fleet intake and dispatch. No installed operator ROMs
or serving Jeeves checkpoints were accessible to this GitHub edit session.
No existing commercial ROMs were downloaded, uploaded, redistributed or
automatically licensed; no hardware, native libretro or production training
qualification is claimed from source code.

The fleet extension lives in `skeleton/ai/training/rom_study.py` and reuses:
- `skeleton.jeeves.game_learning_ingestion` format/metadata concepts
- `skeleton.jeeves.game_emulator_catalog` canonical hardware/core approvals
- `skeleton.jeeves.game_rom_runtime` for the bounded experimental DMG path
- `skeleton.jeeves.game_emulator_training_lab` for genuine replay-audited
  Q-table policy training, controller exploration, counterfactual and boomerang
- `skeleton.jeeves.game_emulator_neural_world` for an independently evaluated
  **candidate** MLP fitted to replay-verified observations, not Jeeves weights.

## Inventory ALL present local single-file ROMs, not imagined collections

On the **machine with the ROMs**, with its actual private library mounted:

```bash
mkdir -p /private/rom-research
python -m scripts.training.rom_study inventory \
  --root /absolute/path/to/owned-rom-library \
  --output /private/rom-research/rom-inventory.json
python -m scripts.training.rom_study verify \
  --manifest /private/rom-research/rom-inventory.json
```

The directory scan enumerates up to 16,384 ordinary entries with bounded depth,
blocks symbolic links, inventories known cartridge/media suffixes, fingerprints
bounded regular files with SHA-256 and labels oversized sources separately.
It does **not** execute any game, extract archive files, follow unknown
content descriptors or assume extension implies correct hardware compatibility.
Current single-file suffix hints: .gb/.gbc/.nes/.sfc/.smc/.md/.gen/.smd/
.sms/.gg/.gba/.nds/.z64/.n64/.v64/.lnx/.a78/.pbp. ZIP, disk images, CD
bundles and larger ROMs remain unresolved in this first path and require the
already governed streamed multi-file content admission and installed core.

**Every new ROM starts with `training_permitted: false` and
`human_reviewed: false`.** Open the private manifest, independently check each
game's origin and actual permission to train/evaluate, and set
`training_permitted: true`, `human_reviewed: true`, a real
`rights_holder`, `review_id`, and a rights basis beginning
`original:`, `license:` or `public-domain:`. A user-editable declaration
records review; it is not proof of ownership. Do not train on copyrighted
commercial ROMs without appropriate authorization. Firmware, copy-protection
keys and proprietary emulator SDKs must be separately lawfully provisioned.
Never commit ROMs, licenses containing secrets, raw game screenshots, or
private inventories to Git.

## Execute actual game-policy training on every approved compatible ROM

```bash
mkdir -p /private/rom-research/candidates
python -m scripts.training.rom_study train-all \
  --manifest /private/rom-research/rom-inventory.json \
  --output-dir /private/rom-research/candidates \
  --runs 12 --steps 12 --neural
```

For each approved, checksum-matched file (maximum 2 MiB inline), try the
bounded interpreter **only** for a Game Boy cartridge that passes its mapper
and checksum admission. Everything else must use an *installed and approved*
libretro core from `SKL_GAME_EMULATOR_REGISTRY`. No fallback reference engine
pretends to execute an incompatible ROM.

The current canonical emulator lab runs each episode and verifies restored
checkpoints, replayed actions, frame digests and finite measured observations
before committing actual tabular Q updates. Its reward is a generic measured
environment signal, **not** automatic detection of a game's genuine win state.
Optionally, the neural world-model trainer rechecks exact evidence and executes
real bounded gradient updates against episode-separated held-out samples.
A rejected predictive model remains a rejected candidate.

Per-ROM output files preserve separate `*-policy.json`, `*-evidence.json`,
optional `*-neural.json` and `*-receipt.json` files, written exclusively
with 0600 permissions. A failed or unsupported ROM is reported as **blocked**,
not included in successful totals. Existing outputs are never overwritten and
the CLI reports a nonzero status if any approved ROM fails. No game binary is
copied into output artifacts.

## Long-run operator follow-up

Runs are bounded and cancellable; monthly/yearly learning is built by
operator-directed repeated passes over individually authenticated sources and
immutable receipts, not unrestricted unsupervised copying or infinite loops.
Use the canonical source-owner checkpoint/resume process for deeper campaigns.
Additional milestones required before "all ROMs trained" is a valid claim:
streamed multi-file/disc intake, lawful source-specific reward definitions,
objective-aware actual game completion/playthrough validation, persistence/
resume across fleet runs, coverage accounting by emulator/version/target,
model-to-model held-out evaluation, and independently governed production
Jeeves checkpoint training.

The ROM fleet's MLP and policy candidates do **not** update the speaking Jeeves
transformer. That separately requires the compiled app, a restored
`SKELETON_OWN` checkpoint, rights-reviewed *text* training examples and the
existing production-training operator procedure:
`docs/ai/JEEVES_PRODUCTION_GAME_TRAINING_RUNBOOK.md`.
