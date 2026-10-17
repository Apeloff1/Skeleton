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

### Real Dragon pixel-level observation

For approved libretro episodes, the trainer now calls the canonical
`inspect_frame()` after each *actual* emulator action. The host validates the
full RGB24 frame and computes 16x16 tile digests and sampled color/luminance
statistics. Dragon records compact per-frame optical evidence, tile diversity,
brightness ratios and a frame sequence identity, without copying screenshots
into model training data. This is **real pixel-level analysis**, not image
understanding by a vision-language model. Game objects, music semantics and
narrative interpretations remain unverified until a separate model witnesses
the original media. Non-native and legacy sessions report missing optics
rather than receiving fabricated observations.

### Independent adversarial LLM review (local checkpoint)

After a ROM is genuinely played and its triangle receipt has been committed,
a **separate** admitted local native transformer can execute three independent
red-team generations against measured training metadata:

```sh
python -m scripts.training.rom_study review-triangle \
  --receipt /private/rom-receipts/rom-<source>-<run>.json \
  --source-sha256 <full-64-hex-source-digest> \
  --reviewer-checkpoint /private/models/independent-reviewer-checkpoint.json \
  --output-dir /private/rom-receipts \
  --max-new-tokens 160
```

The reviewer must be an **actually installed local Skeleton model checkpoint**;
the reviewed data alone cannot create a real model. Three real native model
generations attack source integrity, repetition/causality, and holdout
generalization. The model and its generated token receipts, hashes, and
source-linked output are independently persisted under a new create-only
`triangle-review-*.json` receipt. Each generated judgment is treated as
untrusted; valid JSON must cite an actual trace. Unsupported or malformed
outputs are explicitly flagged for manual review. No review self-certifies
superiority, gameplay success, memory promotion, or trained Jeeves language
weights. This command never invokes external providers or overwrites a
previous review and does not run automatically inside every ROM episode.

The reviewer executes on a local, operator-selected checkpoint. A second
model's **distinctness from Jeeves's production speaking checkpoint** is not
automatically established without a separately pinned production-model
identity; the review records that limitation explicitly.

### One-command supervised training triangle

With an operator-approved frozen snapshot, native libretro core registry,
rights approval manifest, and an installed local reviewer checkpoint:

```sh
python -m scripts.training.rom_study train-triangle \
  --root /private/rom-library \
  --approvals /private/rom-training-approvals.json \
  --output-dir /private/rom-receipts \
  --snapshot /private/rom-receipts/rom-library-snapshot.json \
  --reviewer-checkpoint /private/models/reviewer.json \
  --limit 32 --max-pages 1 --runs 12 --steps 24 \
  --review-tokens 160
```

The campaign performs exact source identity, rights, native core admission,
real replay-audited Q-policy training, Dragon frame-by-frame pixel and
temporal inspection, and three checkpoint-backed adversarial model passes.
A second run with the same frozen snapshot and configuration **reuses only
independently verified Q training receipts**, and **actually replays the
local critic's recorded generations** before calling a previous model review
reproducible. Raw ROM bytes and video frames are not exported by the triangle.

Each printed page includes `cursor`, `next_cursor`, separately measured
gameplay/reviewer statuses, outstanding permission blockers, and a
`review_failures_needing_retry` count. If a model pass fails, the CLI exits
with code 3 **without advancing the cursor**. Retry the same page; approved
ROM source receipts are create-only. For a deliberate continuous foreground
library pass, set `--max-pages 0`; this is not an autonomous unattended
background worker and may take substantial machine resources.

Run `triangle-status --receipt <ROM-receipt> --source-sha256 <full-hash>`
to inspect source-bound Dragon/play/reviewer challenges without loading any
language-model checkpoint. Native model judgments still need independent
human adjudication and do not promote Jeeves production parameters.

Adversarial admission is strict: all three model passes must emit a bounded,
source-referenced structured critique. If a local checkpoint generates
unstructured text or invalid source claims, its native inference receipt is
retained but the campaign exits at the same page with a non-success status.
Use a different `--review-seed` or an independently selected reviewer
checkpoint to obtain a *new* create-only review; do not relabel the old
generation as evidence of completed adversarial scrutiny.

### Candidate data for Jeeves — correlated lens amplification

After the independent native critic has produced **three source-linked
review passes** and its checkpoint is still available, export eight verified
lens perspectives per genuinely executed native episode:

```sh
python -m scripts.training.rom_study export-triangle-corpus \
  --receipt /private/rom-receipts/rom-<source>-<run>.json \
  --review-receipt /private/rom-receipts/triangle-review-<source>-<config>.json \
  --source-sha256 <full-source-sha256> \
  --reviewer-checkpoint /private/models/reviewer.json \
  --output-dir /private/rom-receipts
```

This command **re-executes all three critic model generations** from the
checkpoint to verify their recorded tokens and text, then builds a private
create-only `triangle-corpus-*.json` candidate artifact. Each native
episode yields eight separately labeled visual/audio/controller/reward/
temporal/causal/policy/adversarial views, each with **1/8 of that source
episode's normalized weight**. Each is linked to the original native
trace, receipt and one rights review. There are **zero** new independent
games, zero synthetic rewards, zero leaked heldout steps, and **zero
production Jeeves SGD updates**. Raw critic prose is not accepted as a
ground-truth label; this candidate must still pass the existing Jeeves
human-reviewed corpus admission and actual checkpoint training gates.

### Canonical Jeeves 43-lens semantic routing

The repository already ships authored semantic lenses in
`skeleton/jeeves/agent/semantic_lenses.py`, `semantic_frontier.py`,
`semantic_extreme_lenses.py`, `semantic_research_lenses.py`,
`semantic_plane_lenses.py`, and `semantic_depth_lenses.py`.
`MaximalSemanticRegistry` is the canonical de-duplicated registry,
not a new, competing game-specific list.

The ROM study now uses **up to 43 of these real authored semantic lens
definitions per native episode**, selected by the native maximal router
from six separately source-bound observation summaries (visual, audio,
controller, reward, time/replay and counterfactuals). Each routed lens
preserves its original key, family, activation score, diagnostic question,
failure mode, and catalog identity. Every selection can be deterministically
reconstructed from the same native evidence.

**Important:** the eight measured training lenses remain independent
*measurement projections* and retain their existing normalized weight.
The 43-budget semantic routing is an additional interpretive layer:
film/cinema, gaming, narratology, causal, probability, computational,
social, memory and other semantic operators generate questions and
possible falsifiers. Their answers are **not fabricated from ROM hashes**.
The candidate corpus embeds these questions with an explicit
`not_measured_pending_independent_review` state, without marking them
as supervised ground truth, extra native episodes, new Q updates, or
production transformer steps. The exact number routed depends on
applicability and the actual authored catalog; 43 is the selection budget,
not an invented claim that the repository has only 43 lens definitions.

The candidate format is now `game_triangle_candidate_corpus.v2` and uses
`triangle-corpus-v2-*.json`; previously exported eight-view-only candidates
remain untouched. The `triangle-status` command previews the **actual
canonical keys routed** for the first three episodes, including catalog
identity and selection counts. These semantic questions remain pending
adjudication and cannot by themselves count as newly measured gameplay.

### Reuse all 43 selected lenses from Jeeves' actual authored registry

The 43-per-episode semantic pass uses
`skeleton.jeeves.agent.semantic_maximal.MaximalSemanticRegistry`, not a
second hard-coded list. The canonical registry contains more than 43 named
operators, so **43 is the routed selection size, not the total registry
count**. The eight pre-existing measured gameplay lenses remain distinct;
they are the only supervised numeric evidence views. Semantic lenses
contribute 43 source-linked questions, roles, failure modes and scientific
governance decisions, not fabricated pixel/object/narrative labels.

To pin exactly the 43 canonical lens keys intended for a study, provide an
explicit JSON manifest:

```json
{
  "schema_version": "skeleton.jeeves.semantic_lens_set.v1",
  "lens_keys": ["<exact 43 distinct registered Jeeves semantic lens keys>"]
}
```

Pass `--semantic-lens-set /private/approved-lens-set.json` to
`export-triangle-corpus`. A missing, duplicate, unknown or unregistered
key fails closed. Without the manifest, the existing cue-aware maximal router
selects 43 of Jeeves' authored definitions. Every route is governed through
`SemanticGovernanceBridge`; it cannot claim factual or causal authority.
Changing the selection or the upstream catalog changes the custody digest
and creates a different candidate-corpus filename. The original source
episode still contributes exactly one independent gameplay episode,
regardless of the 43 semantic questions.

You can inspect the **actual 43 selected lens keys, their families,
governance grades and questions**, with independent source-receipt
verification and without loading any language-model checkpoint:

```sh
python -m scripts.training.rom_study triangle-lenses \
  --receipt /private/rom-receipts/rom-<source>-<run>.json \
  --source-sha256 <full-source-sha256> --run-index 0 \
  --output-dir /private/rom-receipts
```

Supplying `--output-dir` creates a strict, create-only
`semantic-lens-set-*.json` manifest of those 43 canonical keys.
That file can be reused through `--semantic-lens-set` at candidate
export. Without `--output-dir`, the command is read-only. Selection
always remains a set of **research questions rather than measured
video semantics or ground-truth training labels**.

### Execute all 43 routed semantic lenses against real model weights

The existing `triangle-lenses` command routes 43 of Jeeves' *authored*
canonical semantic operators and produces questions without model inference.
The new `execute-43-lenses` command performs a separate **native checkpoint
inference for each of the 43 original governed lenses**. It first reproduces
all three adversarial critic generations with the critic's pinned checkpoint,
then invokes the semantic checkpoint once per routed lens.

```sh
python -m scripts.training.rom_study execute-43-lenses \
  --receipt /private/rom-receipts/rom-<source>-<run>.json \
  --review-receipt /private/rom-receipts/triangle-review-<source>-<config>.json \
  --source-sha256 <full-64-digit-source-sha256> \
  --critic-checkpoint /private/models/independent-critic.json \
  --semantic-checkpoint /private/models/jeeves-semantic.json \
  --output-dir /private/rom-receipts \
  --run-index 0 --max-new-tokens 192
```

Specify `--semantic-lens-set /private/approved-lens-set.json` to run your
operator-pinned **exact 43 canonical lens keys** instead of the
evidence-driven 43 chosen by `MaximalSemanticRegistry`. Every question retains
the upstream lens key, governing decision and catalog SHA. The 43 prompts
receive only native pixel/reward/controller/replay **measurements and their
source digests**, not game content they cannot observe. Each result must be
valid source-referenced JSON with an explicit
`unverified_hypothesis` status and a falsification test.

The command saves a create-only `semantic-43-native-*.json` inference
receipt only when all 43 calls produced structurally valid hypotheses.
Re-running the same command loads the original checkpoint and **actually
replays each of the 43 token sequences**. The semantic reviewer model may
share architecture or weights with the critic unless the operator deliberately
supplies a distinct checkpoint; the receipt does not claim independence it
cannot verify. These 43 interpretive hypotheses are not new game observations,
not causal proof, not supervised ground truth, and not production Jeeves
training updates. The previously implemented eight native measurement lenses
continue to be the only source-grounded numerical training projections.

### Forty-three actual native model lens passes

The operator command `execute-43-lenses` runs each of the canonical
43 governed lens questions through a real local Skeleton language-model
checkpoint, after independently replaying the earlier three adversarial
critic generations. Both checkpoints and all source receipts must be
available. Each per-lens result retains its source trace, registered
lens identity, governance decision, generated tokens and model identity;
subsequent invocations replay the complete batch against the same checkpoint.

The native model can return malformed or unstructured text. In that case
all 43 **actual inference receipts** remain stored and replayable, but
`source_referenced_interpretations`, `lens_interpretations_incomplete`
and `all_lens_interpretations_valid` distinguish usable structured
hypotheses from missing/invalid responses. Neither success nor failure
creates independent gameplay data, verifies semantic scene content, or
updates Jeeves' production language-model weights.

### Feed reviewed 43-lens execution into candidate-corpus custody

After `execute-43-lenses` has produced a real `semantic-43-native-*.json`
receipt, extend the existing candidate export with BOTH the review receipt
and its exact local checkpoint:

```sh
python -m scripts.training.rom_study export-triangle-corpus \
  --receipt /private/rom-receipts/rom-<source>-<run>.json \
  --review-receipt /private/rom-receipts/triangle-review-<source>-<config>.json \
  --source-sha256 <full-64-digit-source-sha256> \
  --reviewer-checkpoint /private/models/independent-critic.json \
  --semantic-review-receipt /private/rom-receipts/semantic-43-native-<source>-<session>.json \
  --semantic-checkpoint /private/models/jeeves-semantic.json \
  --output-dir /private/rom-receipts
```

This additional guarded `triangle-corpus-v3-*.json` export binds the 43
native semantic model inferences to the exact source trace, the original
canonical lens catalog, the source critic and the model checkpoint.
The export **actually replays all 43 saved generations** before recording
their digest as a separately inspectable provenance reference. Existing
`v2` eight-measurement / 43-question exports continue to work unchanged.

Model-generated hypotheses stay in their independent review receipt; the
candidate corpus references its digest but **does not copy unverified
hypotheses or falsifiers into target training labels**. Eight native
measurement views retain per-episode normalized weight 1/8 each.
No new independent gameplay examples, synthetic awards, fictional video
semantics or production Jeeves weight updates are introduced.

### Automatically execute the 43 lenses inside the full ROM training campaign

Enable the native 43-lens checkpoint in the existing long-form campaign.
The **critic checkpoint remains a distinct explicit selection** and its
source-bound model outputs are replayed before each semantic session:

```sh
python -m scripts.training.rom_study train-triangle \
  --root /private/rom-library \
  --approvals /private/rom-training-approvals.json \
  --snapshot /private/rom-receipts/rom-library-snapshot.json \
  --output-dir /private/rom-receipts \
  --reviewer-checkpoint /private/models/adversarial.json \
  --semantic-checkpoint /private/models/semantic.json \
  --semantic-all-runs --max-pages 0 \
  --review-tokens 160 --semantic-tokens 192
```

The optional `--semantic-checkpoint` enables the fully wired 43-lens
native model phase. Without `--semantic-all-runs` it analyzes the first
verified native episode per admitted ROM; with it, it executes **43 separate
governed lens inferences for every actual replay-audited episode**. The
`--semantic-lens-set` flag selects an exact 43-key canonical manifest.
`--semantic-seed` and `--semantic-tokens` are independent, versioned
generation controls. New output reports counts and source-linked
`semantic-43-native-*.json` receipts, never fabricated success. Existing
gameplay and critic receipts are reused, with actual local model replay
required for saved critic and semantic outputs.

If the semantic checkpoint fails, any particular lens produces malformed
output, or a source reference changes, the campaign does not advance its
inventory cursor and returns an error. This is intentionally resource-heavy
and operator-run, not a hidden background recording or automatic weight
promotion process. Even a completed 43-lens pass creates hypotheses and
falsification prompts, **not 43 new independent samples**, new reward labels
or trained Jeeves production weights.

#### Actual observation support for the 43 lenses

The canonical lexical router now receives **positive native measurements
only**. It no longer interprets warnings such as "no dialogue" or "no scene
semantics" as evidence that a dialogue, music, camera or scene was observed.
Missing RGB tile inspection and absent counterfactual probes are explicitly
reported as missing modalities, not silently supplied as lens evidence.

Each routed canonical Jeeves lens retains a separate
`native_evidence_support_class`:
`measured_native_cue_present` or
`hypothesis_only_without_matching_native_cue`. The latter may still issue
a diagnostic question, but may not produce a factual training label,
promote confidence, or imply that native video, characters or narration
were recognized. The 43-lens model prompt and candidate corpus carry
this distinction, and `triangle-lenses` reports supported versus
hypothesis-only counts. Existing semantic-routing artifacts are
source/catalog-bound and must be regenerated after routing-policy changes.

Each routed semantic lens now also records the exact native observation IDs,
observation fingerprints, and cue strings responsible for its eligibility.
The cue-provenance sequence has its own source digest, which travels into
the corresponding local model prompt and candidate corpus. Rehashing and
substituting an unrelated frame or observation does not pass route replay.
This is source attribution for *questions*, not a claim of semantic vision
or an independent game sample.

### Auditing all 43 authored lenses across gameplay episodes

Use `triangle-lens-audit` to expose a **cross-episode 43-lens evidence
matrix**, with canonical lens keys, governed lens questions, exact positive
native observation cue counts, hypothesis-only cases, and suggested next
measurements for missing optical frames or controller counterfactual probes.

```sh
python -m scripts.training.rom_study triangle-lens-audit \
  --receipt /private/rom-receipts/rom-<source>-<run>.json \
  --source-sha256 <full-64-character-source-digest> \
  --start-episode 0 --limit 8
```

Supply `--semantic-lens-set /private/approved-lens-set.json` when a manually
approved exact set of 43 keys is needed. Output is read-only and digest-pinned
to the real source evidence and original Jeeves scientific governance.
`next_episode_index` provides bounded pagination (maximum 16 episodes per
request). The audit **does not** claim semantic inference, inspect unrecorded
video, run a language model or inflate independent gameplay examples.

### Preserve the 43 lenses for **every** native gameplay episode

The training campaign's `--semantic-all-runs` mode creates a separate
native-model 43-lens review for each actual gameplay episode. The corpus
exporter now accepts repeated `--semantic-review-receipt` arguments to
retain **all** reviewed episodes rather than just episode zero:

```sh
python -m scripts.training.rom_study export-triangle-corpus \
  --receipt /private/rom-receipts/gameplay.json \
  --review-receipt /private/rom-receipts/critic.json \
  --source-sha256 <full-source-sha256> \
  --reviewer-checkpoint /private/models/critic.json \
  --semantic-checkpoint /private/models/semantic.json \
  --semantic-review-receipt /private/rom-receipts/semantic-episode-0.json \
  --semantic-review-receipt /private/rom-receipts/semantic-episode-1.json \
  --output-dir /private/rom-receipts
```

The same reviewer checkpoint **actually replays every saved model generation**
before export. For multiple episodes, the new `triangle-corpus-v4-*.json`
records one uniquely identified, route-matching and complete 43-lens review
for **every** native episode, in original source order. Duplicate/missing
episode reviews, stale canonical route hashes, mixed models, or partially
structured hypotheses are rejected. Single-review v3 and observation-only
v2 exports remain supported. This feature also recognizes the separately
configured extended 200-lens budget when the installed canonical registry
and corresponding model receipts support it. As before, the measured
eight-lens Q-training evidence is not multiplied and none of the language
model hypotheses are promoted to supervised truth labels.

### Full 200-lens canonical Jeeves training triangle

The original 43-lens mode is retained for existing replay receipts. The
extended mode now routes **all 200 authored definitions from
`skeleton.jeeves.agent.lens_system.LensCatalog`**, preserving each original
lens ID, family, authority and required outputs. The larger
`MaximalSemanticRegistry` remains available for legacy 43-lens routing, but
the extended mode does not choose an arbitrary 200-lens subset of it.
This is a complete 200-definition first-order catalog, not an assertion that
the entire application contains only 200 semantic operators. A lens that lacks positive native cue support is an
unverified question, *not* an observed game feature.

Inspect and pin one episode's full selection with:

```bash
python -m scripts.training.rom_study triangle-lenses \
  --receipt /private/rom-receipts/rom-source-run.json \
  --source-sha256 <64-character-source-hash> \
  --lens-count 200 --output-dir /private/rom-receipts
```

Audit the coverage of all 200 *routed questions* across up to 16 native
episodes per page using `triangle-lens-audit --lens-count 200`.
Each lens retains original catalog and scientific-governance identity,
positive cue provenance, measurable coverage and missing-evidence status.

Execute **200 actual local transformer generations** for an audited episode:

```bash
python -m scripts.training.rom_study execute-200-lenses \
  --receipt /private/rom-receipts/rom-source-run.json \
  --review-receipt /private/rom-receipts/triangle-review-source.json \
  --source-sha256 <64-character-source-hash> \
  --critic-checkpoint /private/models/critic.json \
  --semantic-checkpoint /private/models/jeeves-semantic.json \
  --output-dir /private/rom-receipts
```

The checkpoint must actually be installed. The first pass records 200
model-generated hypotheses linked to exact native traces and questions; a
repeat must reproduce all 200 stored generations. Critic review itself is
replayed before semantic model execution. Invalid or unsupported hypotheses
remain unverified and block supervised corpus admission.

Run the longer foreground campaign with
`train-triangle --semantic-checkpoint ... --semantic-lens-count 200
--semantic-all-runs`, or use
`export-triangle-corpus --semantic-lens-count 200` after a recorded and
replayed 200-lens review. The original eight measured gameplay lenses remain
the only eight numeric training-view rows per episode. All 200 semantic
lenses are interpretive **questions**, not 200 independent games or newly
measured target labels. Model promotions remain separately gated.

#### Canonical 200-lens full-catalog wiring (current)

The extended mode now enumerates **all 200 IDs** returned by the canonical
`LensCatalog.all()` and fails closed if the catalog grows, shrinks, drops
required outputs or repeats IDs. Every lens carries original family,
authority, provenance-linked cue matching and a pending independent
interpretive question. Unsupported native visual, narrative, music or game
mechanics are explicitly *hypothesis only*. A 200-key operator manifest must
be an exact permutation of those 200 IDs; it cannot omit difficult lenses.

New CLI `triangle-lenses`, `triangle-lens-audit`, `train-triangle` and
`export-triangle-corpus` requests **default to 200 lenses**. Use
`--lens-count 43` or `--semantic-lens-count 43` for existing 43-lens
receipts and older studies. The explicit `execute-43-lenses` command stays
available; `execute-200-lenses` invokes a real local language-model generation
for each of the 200 catalog definitions when an installed checkpoint is
provided. The independent model outputs are hypotheses and cannot increase
the eight measured native source perspectives or update Jeeves weights by
themselves.

The one-command campaign now defaults to all native episodes whenever a
semantic checkpoint is supplied: **200 operator lenses × each independently
verified gameplay episode**. The previously optional
`--semantic-all-runs` flag remains accepted. To conserve resources in an
explicit legacy/diagnostic run, select `--semantic-first-run-only`.
The command remains a foreground workload, creates no independent samples
from repeated questions, and requires actual local checkpoint inference.

### 200-lens crash-safe continuation and evidence semantics

The full 200-lens mode is explicitly bound to a **real installed semantic
checkpoint** and, within a `train-triangle` page, runs against **every
measured native episode**. It will not silently pass a 200-lens campaign with
only a three-pass critic and no semantic model.

Long sessions use immutable, private, source/route/model/seed-bound files named
`semantic-lens-progress-<session>-<step>.json`. This stores each actually
generated native inference immediately. On restart, the runtime verifies a
contiguous prefix, reconstructs the same canonical 200-lens route and **replays
all saved native generations on the exact installed local checkpoint** before
continuing with the remaining lenses. Corrupted or gapped checkpoints halt
instead of fabricating coverage. Journals are separate from final reviewed
200-lens receipts and do not by themselves authorize corpus promotion.

For a smaller legacy operator workflow, `--semantic-lens-count 43` is still
available. The 200 canonical semantic lenses remain **questions and
hypotheses**. Eight numerical observation families are still the only
measured gameplay candidate training rows per episode; 200 semantic
interpretations do not create 200 new independent samples or change
production Jeeves parameters.

### Inspect 200-lens progress without generating more tokens

```sh
python -m scripts.training.rom_study triangle-lens-progress \
  --receipt /private/rom-receipts/rom-<source>-<run>.json \
  --review-receipt /private/rom-receipts/triangle-review-<source>-<config>.json \
  --source-sha256 <full-source-sha256> \
  --semantic-checkpoint /private/models/semantic.json \
  --output-dir /private/rom-receipts \
  --run-index 0 --seed 0 --max-new-tokens 192
```

This read-only command validates the native training report, canonical
200-lens route, three critic findings, session fingerprint, and contiguous
per-lens immutable checkpoint journal. It reports **all 200 original lens
keys**, distinguishing persisted, still-pending and final-receipt-confirmed
generations. It does **not** execute or replay the language model; only the
actual `execute-200-lenses`/foreground campaign resume path can establish
replay fidelity. Legacy complete native inference receipts created before
per-lens journaling remain readable, explicitly identified as such.
