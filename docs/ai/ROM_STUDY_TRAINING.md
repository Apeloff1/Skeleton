# All available ROMs — Jeeves and Dragon training operator guide

This pipeline adds **real operator-authorized gameplay Q-policy learning** over
local ROM libraries. It does NOT imply all ROMs are legally available,
supported, playable to completion, or eligible for machine-learning use.
SDK documentation and ROM content have independent rights reviews.

## Ownership and scope

The ROM pipeline reuses the canonical emulator catalogue and worker,
\`skeleton/jeeves/game_emulator_catalog.py\` and
\`skeleton/jeeves/game_emulator_host.py\`. It never executes unknown ROMs or
native libraries in the inventory step. Training is owned by the existing
\`skeleton/jeeves/game_emulator_training_lab.py\` and its finite replay-based,
held-out-audited Q-policy learner. It produces candidate neural data, **not**
Jeeves transformer weight updates or verified game mastery.

## 1. Inventory what is actually on the local host

\`\`\`sh
python -m scripts.training.rom_study inventory \
  --root /private/rom-library --limit 64
\`\`\`

Results show exact relative path, SHA-256, size, extension, review state and
a \`next_cursor\` when the scan has more pages. Re-run with
\`--cursor "last/path/from/next_cursor"\`. File bytes are hashed in bounded
streams, never exported as ROM content. Enumeration excludes symlinks and
undeclared suffixes. CUE, GDI, M3U and other disc descriptors are surfaced
but require explicit multi-file bundle admission, not single-file Q-training.
Ambiguous .bin/.iso/.rom/.zip entries always require manually declared
hardware/core identity. Archive contents are not automatically extracted.

There is a bounded maximum of 100,000 candidate files and 10,000 directories
per selected root. Divide larger libraries into separate operator-approved
roots. Inventory does not establish a working emulator.

## 2. Rights and local emulator approval

Create an operator-private \`/private/rom-training-approvals.json\`:

\`\`\`json
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
\`\`\`

No entry is approved automatically. A playable copy is not itself evidence of
permission to train on copyrighted text, audiovisual output or extracted
assets. Proprietary ROMs without rights authorization remain blocked.

Configure and independently approve the exact installed libretro core and
legitimate firmware through the existing \`SKL_GAME_EMULATOR_REGISTRY\`
contract. \`core_id\` and \`target_id\` must agree with the approved core.
Core installation, extension hints, license permission, runtime compatibility,
measured policy updates and successful game completion are separate facts.

## 3. Run every eligible local candidate through the existing emulator lab

Create a private operator-owned output directory with mode 0700:

\`\`\`sh
mkdir -p /private/rom-receipts
chmod 700 /private/rom-receipts
export SKL_GAME_EMULATOR_REGISTRY=/private/approved-cores.json
python -m scripts.training.rom_study train-all \
  --root /private/rom-library \
  --approvals /private/rom-training-approvals.json \
  --output-dir /private/rom-receipts \
  --max-pages 1 --limit 32 --runs 12 --steps 24
\`\`\`

Read \`next_cursor\` from JSON output, then re-run with \`--cursor\` to
continue. Use \`--max-pages 0\` only when you intentionally want a potentially
lengthy **foreground** scan of every page; this is not an automatic
background job. Each call enforces bounded resources. Per-ROM results are
stored create-only. A previously recorded result is hash and evidence
checked before being treated as a valid prior run; it is never silently
replaced. A newly seen ROM with no approved rights, unsupported format,
missing core, invalid source or failed replay receives an explicit blocked
state, not a fabricated training receipt.

Recorded outcomes distinguish:
- \`q_policy_updated_with_receipt\`: replay-audited actual numeric Q updates
- \`q_policy_executed_no_updates\`: an executed episode without measured Q updates
- \`previous_verified_receipt_no_reexecution\`: verified earlier result
- \`no_training_rights_review\` and other blocked states

The lab retains per-run snapshot identities, reverse replay evidence,
observed audiovisual state differences, held-out policy evaluation, and
training-only numerical candidate samples. It never guesses universal
victory registers, console compatibility or a game ending based on visual
novelty.

## 4. Model weights and Dragon

The ROM learner can generate actual per-title tabular policy updates on a
properly installed host. It **does not** fine-tune Jeeves's speaking model.
Use the existing attested production trainer and
\`docs/ai/JEEVES_PRODUCTION_GAME_TRAINING_RUNBOOK.md\` for independent
checkpoint-derived candidate weight updates and promotion. ROM evidence
cannot bypass dataset provenance, legal review, contamination screening or
human promotion authority. Dragon may use reviewed observations in its
existing knowledge/evidence plane; no automatic almanac or weight promotion
is implied by these receipts.

### Limits

- More than 2 GiB per ROM, multi-file discs, missing cores/firmware, and
  unknown extensions remain explicitly unsupported by this batch path.
- Repeated inventory pages rescan the root. Freeze a ROM library for a
  complete crawl; partition mutable libraries.
- A measured Q-policy update is a fact about that observed training run,
  not proof of generalized game-playing capability.
- Only ROM names/hashes and locally generated receipts belong in this
  operator path. Never commit ROM bytes, BIOS files or private manifests.
