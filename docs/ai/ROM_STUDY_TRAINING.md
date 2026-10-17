# All available ROMs — Jeeves and Dragon training operator guide

This pipeline adds **real operator-authorized gameplay Q-policy learning** over
local ROM libraries and an optional second stage of **actual candidate neural
world-model optimizer updates** from replay-verified episodes. Neither
stage modifies production Jeeves speaking weights. It does NOT imply all ROMs are legally available,
supported, playable to completion, or eligible for machine-learning use.
SDK documentation and ROM content have independent rights reviews.

## Ownership and scope

The ROM pipeline reuses the canonical emulator catalogue and worker,
`skeleton/jeeves/game_emulator_catalog.py` and
`skeleton/jeeves/game_emulator_host.py`. It never executes unknown ROMs or
native libraries in the inventory step. Training is owned by the existing
`skeleton/jeeves/game_emulator_training_lab.py` and its finite replay-based,
held-out-audited Q-policy learner. It produces candidate neural data, **not**
Jeeves transformer weight updates or verified game mastery.

## 1. Inventory what is actually on the local host

```sh
python -m scripts.training.rom_study inventory \
  --root /private/rom-library --limit 64
```

Results show exact relative path, SHA-256, size, extension, review state and
a `next_cursor` when the scan has more pages. Re-run with
`--cursor "last/path/from/next_cursor"`. File bytes are hashed in bounded
streams, never exported as ROM content. Enumeration excludes symlinks and
undeclared suffixes. CUE, GDI, M3U and CCD disc descriptors are surfaced and can now enter
training only after approval of their **entire exact companion bundle**.
TOC/MDS remain unsupported by the canonical content owner.
Ambiguous .bin/.iso/.rom/.zip entries always require manually declared
hardware/core identity. Archive contents are not automatically extracted.

There is a bounded maximum of 100,000 candidate files and 10,000 directories
per selected root. Divide larger libraries into separate operator-approved
roots. Inventory does not establish a working emulator.

### Frozen inventory for large libraries

Repeatedly re-enumerating a 100,000-ROM library for every page is inefficient.
A private create-only snapshot stores exact paths, byte lengths and SHA-256
identities without copying ROM contents:

```sh
python -m scripts.training.rom_study freeze-inventory \
  --root /private/rom-library \
  --output-dir /private/rom-receipts \
  --name rom-library-snapshot.json

python -m scripts.training.rom_study inventory \
  --root /private/rom-library \
  --snapshot /private/rom-receipts/rom-library-snapshot.json
```

Only the page being consumed is rehashed against its pinned source identity.
Changing, replacing or deleting a ROM makes that source ineligible until a new
snapshot and independent approval are issued. The snapshot is read once per
CLI invocation and serves all foreground pages. It does not grant training
permission or preserve the actual ROM data.

## 2. Rights and local emulator approval

Create an operator-private `/private/rom-training-approvals.json`:

```json
{
  "schema_version": "skeleton.jeeves.rom_training_approval.v1",
  "roms": [
    {
      "sha256": "replace-with-actual-64-character-hash",
      "content_size_bytes": 32768,
      "target_id": "game_boy",
      "core_id": "gambatte",
      "rights": {
        "rights_holder": "actual documented rights holder",
        "rights_basis": "original:author-owned-homebrew",
        "review_id": "independent-human-review-001",
        "training_permitted": true,
        "human_reviewed": true
      }
    }
  ]
}
```

For an original homebrew disc with approved companion files, first inspect
its exact **per-game directory**, rather than an entire collection containing
unrelated discs:

```sh
python -m scripts.training.rom_study inspect-bundle \
  --root /private/rom-library/original-disc-game \
  --entrypoint original-disc.cue
```

This pins every file in the folder using the canonical streaming multi-file
content verifier without executing any emulator. Copy the returned
`bundle_sha256` into the corresponding ROM approval as a new
`"bundle_sha256": "<64-hex-digest>"` field. The `sha256` field in the
approval remains the **entrypoint file SHA-256**, as shown in the inventory.
The rights review must cover **every file** in the declared disc bundle, not
just the small descriptor. Changing a companion invalidates the approval
and changes the run's idempotency identity. The original native qualification
script uses this same content-verification owner. An unrelated extra file in
the game directory also changes the bundle digest, so keep each game isolated
in its own subdirectory. Directory trees are bounded to 96 content files
and 4 GiB total by the existing emulator owner.

No entry is approved automatically. A playable copy is not itself evidence of
permission to train on copyrighted text, audiovisual output or extracted
assets. Proprietary ROMs without rights authorization remain blocked.

Configure and independently approve the exact installed libretro core and
legitimate firmware through the existing `SKL_GAME_EMULATOR_REGISTRY`
contract. `core_id` and `target_id` must agree with the approved core.
Core installation, extension hints, license permission, runtime compatibility,
measured policy updates and successful game completion are separate facts.

## 3. Run every eligible local candidate through the existing emulator lab

Create a private operator-owned output directory with mode 0700:

```sh
mkdir -p /private/rom-receipts
chmod 700 /private/rom-receipts
export SKL_GAME_EMULATOR_REGISTRY=/private/approved-cores.json
python -m scripts.training.rom_study train-all \
  --root /private/rom-library \
  --approvals /private/rom-training-approvals.json \
  --output-dir /private/rom-receipts \
  --snapshot /private/rom-receipts/rom-library-snapshot.json \
  --max-pages 1 --limit 32 --runs 12 --steps 24 \
  --neural-world --neural-epochs 4 --neural-width 8
```

Read `next_cursor` from JSON output, then re-run with `--cursor` to
continue. Use `--max-pages 0` only when you intentionally want a potentially
lengthy **foreground** scan of every page; this is not an automatic
background job. Each call enforces bounded resources. Per-ROM results are
stored create-only. A previously recorded result is hash and evidence
checked before being treated as a valid prior run; it is never silently
replaced. A newly seen ROM with no approved rights, unsupported format,
missing core, invalid source or failed replay receives an explicit blocked
state, not a fabricated training receipt.

Recorded outcomes distinguish:
- `q_policy_updated_with_receipt`: replay-audited actual numeric Q updates
- `q_policy_executed_no_updates`: an executed episode without measured Q updates
- `previous_verified_receipt_no_reexecution`: verified earlier result
- `no_training_rights_review` and other blocked states

The lab retains per-run snapshot identities, reverse replay evidence,
observed audiovisual state differences, held-out policy evaluation, and
training-only numerical candidate samples. With `--neural-world`, the existing
`game_emulator_neural_world` performs actual gradient steps only after
independently verifying source receipts, split-by-episode evaluation and
finite resource budgets. A failure is recorded as
`candidate_training_blocked` while retaining honest Q-policy evidence.
A successful neural run remains `candidate_trained_requires_independent_review`
and can report a measured held-out predictive gain (not gameplay mastery). It never guesses universal
victory registers, console compatibility or a game ending based on visual
novelty.

## 4. Model weights and Dragon

The ROM learner can generate actual per-title tabular policy updates and
optional separately trained candidate neural world models on a properly
installed host. It **does not** fine-tune Jeeves's speaking model.
Use the existing attested production trainer and
`docs/ai/JEEVES_PRODUCTION_GAME_TRAINING_RUNBOOK.md` for independent
checkpoint-derived candidate weight updates and promotion. ROM evidence
cannot bypass dataset provenance, legal review, contamination screening or
human promotion authority. Dragon may use reviewed observations in its
existing knowledge/evidence plane; no automatic almanac or weight promotion
is implied by these receipts.

### Limits

- More than 2 GiB per file, more than 4 GiB per disc bundle, unsupported
  disc descriptors (including TOC/MDS), missing cores/firmware, and unknown
  extensions remain blocked. CUE/GDI/CCD/M3U are admitted only with exact
  companion-bundle rights review and native core support.
- Repeated inventory pages rescan the root. Freeze a ROM library for a
  complete crawl; partition mutable libraries.
- A measured Q-policy update is a fact about that observed training run,
  not proof of generalized game-playing capability.
- Only ROM names/hashes and locally generated receipts belong in this
  operator path. Never commit ROM bytes, BIOS files or private manifests.

## Training triangle: Dragon viewing + Jeeves playing + adversarial review

Each **real replay-audited native emulator** run now emits a source-bound
`training_triangle` inside its create-only ROM receipt. The triangle indexes
eight non-destructive lenses: visual states, audio ambience, controller actions,
reward/consequence, temporal reversal, causal counterfactuals, policy progress,
and adversarial boundaries. It checks the ten native replay gates, receipt
hashes, Q-update counts, unique training projections, heldout exclusion, native
probe boundaries, reverse checkpoints, and boomerang evidence.

The three vertices have **different proof obligations**:

1. **Dragon companion observer:** exact frame/audio telemetry and sequence
   digests form a viewing queue; the system **does not yet decode/watch pixels
   semantically or attest that a visual AI viewed the game**. A separate media
   viewer must supply a real witness before that vertex can pass.
2. **Jeeves playing/simulation:** counts actual emulator actions, verified
   reverse replay steps, and real native counterfactual/controller probes.
   These are *not* synthesized playthroughs or game-completion evidence.
3. **Adversarial reviewer:** independently reconstructs deterministic invariants
   and emits challenge tasks for missing training angles/probes. This is
   implemented scrutiny, **not an executed second reviewer LLM**. Independent
   model criticism remains pending.

Repetition and lens transformations **amplify interpretations, not sample
count**. Every lens points to one unique native trace and receipt; revisits
add zero independent examples and zero extra weight updates. Training examples
stay in the original native sample corpus, and heldout data stays excluded.
Corrupted/mismatched triangles invalidate previously saved real lab receipts,
rather than letting a fabricated review certify training or promotion.
This mechanism does not update the production Jeeves language model.
