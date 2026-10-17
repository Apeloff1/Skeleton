# All available local ROMs: Jeeves/Dragon learning admission

**Implemented:** deterministic local candidate census, rights-granted Q-policy
training on the existing replay-audited emulator lab, private durable candidate
receipts, extension / hardware readiness checks and resumable pages.
**Not implemented:** universal emulator compatibility, automatic game completion,
training the serving Jeeves neural weights from ROMs, training-content rights
inference, commercial game copying or acquiring licensed firmware.

This extension is in \`skeleton/ai/training/rom_study.py\` and consumes the
**canonical** \`game_emulator_catalog\`, \`game_emulator_host\`,
\`GameEnvironmentRequest\` and \`game_emulator_training_lab\` owners. It does
not create a second emulator, learning model or provider boundary.

## 1. Inventory an operator-selected local ROM library

\`\`\`bash
python -m scripts.training.rom_study inventory \
  --root /private/rom-library --limit 64
\`\`\`

The output reports actual filename, SHA-256, length, extension, review state,
and \`next_cursor\` for the next page. Discovery is bounded to 100,000
candidate files and 10,000 directories per declared root, skips symlinks,
reads files as fixed-memory streams and **never exports ROM content**. Use
several separately approved roots when necessary. Unknown extensions are not
promoted into game images; the admitted extension registry comes from the
existing emulator catalog. Descriptor-based multisession discs (CUE/GDI/CCD
and similar) remain visible but are blocked from the single-file training
path until an exact companion bundle has been approved.

Continue with the returned cursor:
\`\`\`bash
python -m scripts.training.rom_study inventory \
  --root /private/rom-library --cursor "your/last.rom" --limit 64
\`\`\`

An extension hint is not proof of a valid ROM, installed emulator, working
firmware, gameplay compatibility or training rights.

## 2. Approve ROM source rights and exact platform/core binding

Save JSON **outside the repository** and review real permission to train on
each specific image. A lawful ability to play a copy is **not automatically**
permission to reuse its contents for model training. For restricted or
commercial ROMs lacking an appropriate grant, do not add a training approval.

\`\`\`json
{
  "schema_version": "skeleton.jeeves.rom_training_approval.v1",
  "roms": [
    {
      "sha256": "replace-with-exact-64-character-sha256",
      "content_size_bytes": 32768,
      "target_id": "game_boy",
      "core_id": "gambatte",
      "rights": {
        "training_permitted": true,
        "human_reviewed": true,
        "rights_holder": "Real rights holder",
        "rights_basis": "original:author-owned homebrew",
        "review_id": "documented-operator-rights-review"
      }
    }
  ]
}
\`\`\`

Use actual \`core_id\` and \`target_id\` from
\`skeleton.jeeves.game_emulator_catalog.GameEmulatorRegistry.catalog()\`.
Install and explicitly approve the exact libretro core and any lawfully
supplied firmware before running. The core must match the local OS/CPU, and
an exact extension hint must exist. Unsupported graphics, missing BIOS,
unapproved toolchain, incompatible cartridge or invalid savestate fails
closed and remains in the report.

## 3. Run real measured learning over the collection

Create a **private, operator-owned mode 0700** results directory:
\`\`\`bash
mkdir -p /private/rom-training-receipts
chmod 700 /private/rom-training-receipts
export SKL_GAME_EMULATOR_REGISTRY=/private/approved-libretro-cores.json
\`\`\`

Start with a bounded foreground page:
\`\`\`bash
python -m scripts.training.rom_study train-all \
  --root /private/rom-library \
  --approvals /private/rom-training-approvals.json \
  --output-dir /private/rom-training-receipts \
  --limit 32 --max-pages 1 --runs 12 --steps 24
\`\`\`

The command prints a continuation cursor and a status for **each** candidate.
Resume using \`--cursor\` and the latest printed \`next_cursor\`. Per-ROM
receipts are create-only and already-recorded results are not automatically
trained again. To attempt every eligible candidate over all pages in one
foreground invocation, use \`--max-pages 0\`; this is NOT a detached or
automatically scheduled job, and host compute, disk and process resources must
be provisioned before such a potentially long operation. Every training run
still enforces the canonical lab's finite safety/resource budgets. Changing
a training configuration creates a new candidate identity without overwriting
earlier records.

The pipeline hashes the input **again** before training; selects only the
operator-approved core and hardware mapping; admits small files through
canonical archive inspection, or streams larger standalone images through
canonical private materialization; constructs an exact
\`GameEnvironmentRequest\`; runs the existing emulator lab with savestate,
reverse replay and held-out policy evaluation; and saves the actual
Q-update and replay evidence only after the run returns. A core failure is
reported as a failed item and does not impersonate successful training.

## 4. What this teaches Jeeves and Dragon now

The existing emulator lab performs real observed **tabular Q-policy updates**
per eligible ROM and produces replay-verified numeric
\`neural_candidate_dataset\` rows. These are **candidates**, not updates to
the Jeeves speaking transformer. Source-specific memory addresses and victory
conditions are not guessed: visual novelty is not proof of winning a game.
Cross-game knowledge and Dragon's almanac still require independent review
and promotion through their original owners.

For actual Jeeves neural weight training, a separately attested live checkpoint,
approved compatible corpus, production candidate-trainer execution and
independent evaluation/promotion are still required. Consult
\`docs/ai/JEEVES_PRODUCTION_GAME_TRAINING_RUNBOOK.md\`.
The ROM receipts do not bypass the trainer's rights, checkpoint or
held-out contamination boundaries and cannot be directly called
a fine-tuned transformer.

## Technical limitations

- Native core execution only occurs on the operator's properly configured host.
- ROMs over 2 GiB, multi-file discs needing companion closure, encrypted archives,
  or unsupported cores remain explicitly blocked.
- Retries are idempotent with create-only per-source receipts, but collection
  inventory re-scans for each page; ROM additions/removals can change the
  cursor sequence. Re-inventory after mutable collections change.
- One ROM is one source, not a new general-purpose model. Training scores,
  goals and transfer across titles need independent held-out testing.
- Do not commit proprietary game images, BIOS, copied source, training
  manifests bearing sensitive private paths, or raw gameplay assets to Git.
