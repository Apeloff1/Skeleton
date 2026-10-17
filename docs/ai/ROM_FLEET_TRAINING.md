# ROM fleet — evidence-first Jeeves/Dragon training

This is the **operator-run** route for all locally available, rights-approved
ROMs which have an installed and approved emulator. It is not a downloader or
a source of commercial game licenses. No ROM library, native emulator core or
production Jeeves checkpoint was accessible during the GitHub development
session; code changes do not constitute actual training.

## What exists

- `skeleton.ai.training.rom_study`: SHA-256 census; explicit rights manifest;
  approved libretro-core and firmware checks; native replay-audited game Q-policy
  updates; optional bounded neural-world candidate optimizer; create-only
  evidence receipts with per-ROM failure reasons.
- `skeleton.ai.training.rom_inventory_snapshot`: frozen, private, hash-pinned
  library census for large collections; per-page source revalidation.
- `skeleton.ai.training.rom_fleet_audit`: independently rechecks source
  identities, rights-manifest identity, frozen inventory identity, receipts,
  model-promotion boundaries and per-ROM measurable update counts.
- `skeleton.jeeves.game_emulator_operator_content`: exact local disc folders
  with all companion-file hashes; this is not authorization to train them.
- `skeleton.jeeves.game_emulator_training_lab`: the pre-existing actual
  policy learner with replay and held-out audit. Optional neural-world
  candidates use the pre-existing `game_emulator_neural_world` optimizer.
  **Neither component updates the production Jeeves speaking transformer.**

An image whose rights, emulator, source bytes, replay, or held-out evidence
are unavailable must remain visible as **blocked**, **not completed**.

## Operator commands (current CLI)

First, create a private operator-owned directory and select an actual local
library path (not a repository directory):

```sh
mkdir -p /private/rom-research
chmod 700 /private/rom-research

python -m scripts.training.rom_study inventory \
  --root /absolute/path/to/rom-library --limit 64
```

For a large library, freeze a content-free manifest once:

```sh
python -m scripts.training.rom_study freeze-inventory \
  --root /absolute/path/to/rom-library \
  --output-dir /private/rom-research \
  --name rom-snapshot.json

python -m scripts.training.rom_study inventory \
  --root /absolute/path/to/rom-library \
  --snapshot /private/rom-research/rom-snapshot.json \
  --limit 64
```

For a CUE, GDI, CCD or M3U descriptor, independently inspect its complete
companion bundle before rights approval:

```sh
python -m scripts.training.rom_study inspect-bundle \
  --root /absolute/path/to/rom-library/disc-folder \
  --entrypoint original-game.cue
```

This prints a content bundle digest and individual file hashes. No ROM or
disc data is printed. Review every companion file, not just the descriptor.
The digest is stored in a rights approval as `bundle_sha256`, in addition
to `sha256` for the entrypoint descriptor.

## Explicit rights manifest

Create `/private/rom-research/rights.json` using only demonstrably
training-authorized games. Example for an independently reviewed,
author-owned game:

```json
{
  "schema_version": "skeleton.jeeves.rom_training_approval.v1",
  "roms": [
    {
      "sha256": "actual-64-character-sha256",
      "content_size_bytes": 32768,
      "target_id": "game_boy",
      "core_id": "gambatte",
      "rights": {
        "rights_holder": "Original homebrew author",
        "rights_basis": "original:author-owned-game",
        "review_id": "human-review-001",
        "human_reviewed": true,
        "training_permitted": true
      }
    }
  ]
}
```

The `sha256` must be replaced by the real full SHA-256; the example is not a
working license or source. For a multi-file disc, add the exact
`"bundle_sha256": "actual-64-character-bundle-digest"` to the same approval
object. Do **not** treat ROM ownership or emulator availability as a grant
to learn from copyrighted audio, text, artwork or gameplay.

Configure the existing `SKL_GAME_EMULATOR_REGISTRY` with a trusted local
core and lawfully supplied firmware. No native execution occurs during
inventory, freezing or auditing.

## Run actual reviewed training

```sh
export SKL_GAME_EMULATOR_REGISTRY=/private/approved-libretro-cores.json

python -m scripts.training.rom_study train-all \
  --root /absolute/path/to/rom-library \
  --snapshot /private/rom-research/rom-snapshot.json \
  --approvals /private/rom-research/rights.json \
  --output-dir /private/rom-research \
  --limit 32 --max-pages 1 --runs 12 --steps 24 \
  --neural-world --neural-epochs 4 --neural-width 8
```

This performs **actual emulator episodes, measured tabular Q updates, and
optional candidate neural optimizer updates** on compatible approved content.
The Q policy and neural candidate are different learned artifacts; a positive
gradient count does not establish learned game mastery or imply production
Jeeves model weights were changed.

For the next page, pass the printed `next_cursor` to `--cursor`. Setting
`--max-pages 0` iterates all pages **in the foreground**, subject to bounded
per-ROM resource limits. It is not a scheduled background service. Each ROM
receives an exact create-only private JSON receipt; an existing result is
checked before reuse and cannot be overwritten with a different run.

## Independently audit completed sources and gaps

```sh
python -m scripts.training.rom_study audit-fleet \
  --root /absolute/path/to/rom-library \
  --snapshot /private/rom-research/rom-snapshot.json \
  --approvals /private/rom-research/rights.json \
  --output-dir /private/rom-research --limit 64
```

Inspect `next_cursor` and continue to audit the next page. Audit checks
source bytes again, source/rights/snapshot identity, Q-training receipts and
neural candidate evidence. It does not execute the games.

For an entire immutable inventory without manually paging:

```sh
python -m scripts.training.rom_study audit-fleet \
  --root /absolute/path/to/rom-library \
  --snapshot /private/rom-research/rom-snapshot.json \
  --approvals /private/rom-research/rights.json \
  --output-dir /private/rom-research --limit 64 --max-pages 0
```

This reuses the verified snapshot and rights manifest across all pages,
reporting distinct source counts, measured Q updates, neural candidates,
duplicate identities, stale receipts and missing reviews. A non-null
`next_cursor` after limiting the page count means the fleet audit
remains incomplete. Execution coverage is not game-mastery coverage.

Coverage is **per distinct verified source on that page**; aliases and
repeated training receipts never inflate the denominator. Outcomes separate
`verified_q_policy_updated`, `verified_executed_without_q_update`,
`approved_but_no_receipt`, `rights_review_required`,
`source_identity_changed`, `duplicate_source_inventory_alias`, and
`invalid_or_stale_receipt_only`. Such a coverage percentage is **not**
the percentage of the entire software project completed or proof of
gameplay success.

## A locally available original training proof path

The separate, existing `scripts/accept_original_rom_ai_pipeline.py`
can build a first-party original Game Boy game, run its actual interpreted
instructions, perform replay-verified Q updates and train a local candidate
neural-world model with episode-separated held-out evaluation:

```sh
python scripts/accept_original_rom_ai_pipeline.py \
  --output-directory /private/rom-research/original-seed-42 \
  --seed 42 --max-runs 12 --episode-steps 12 \
  --neural-epochs 4 --neural-width 8
```

Use an output directory that does not already exist, and run on the real
operator host. The generated original game is not a substitute for other
ROMs or proof of production model promotion. Actual Jeeves speaking-model
fine-tuning still needs a separately attested live checkpoint and independent
rights-reviewed training/evaluation through
`docs/ai/JEEVES_PRODUCTION_GAME_TRAINING_RUNBOOK.md`.

**Never commit ROMs, proprietary firmware, keys, extracted proprietary
assets, operator-rights manifests, private paths, or model checkpoints.**
