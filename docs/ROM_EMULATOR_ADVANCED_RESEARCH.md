# Advanced ROM emulator training research — measured, bounded, non-production

This is the advanced counterpart to
[ROM emulator completion](ROM_EMULATOR_COMPLETION.md) and
[the original training laboratory](ROM_EMULATOR_TRAINING_LAB.md).

**Implementation status, 15 October 2026:** source committed to the draft PR,
not compiled or run on real ROMs, not tested here and not authorized to modify
production Jeeves/transformer weights. New numerical neural-world code can
execute *real* parameter optimization when invoked locally, but that code's
existence is **not** a training receipt, learned game capability, native-core
readiness or promotion approval.

## Four separate source-execution pathways

| Command | Actual operation | Training effect |
| --- | --- | --- |
| `train-emulator-deep` | Approved native/experimental DMG episodes, real checkpoint rewind audits, measured counterfactuals and historical replays | **Actual bounded Q-table updates** only |
| `experiment-emulator` | Independent saved-state control groups, repeated action-duration/order sequences, live video/audio and optional operator-chosen memory bytes | **No weight updates**; actual research measurements |
| `compare-emulator-cores` | Same locally admitted ROM, exact action sequence, repeated on 2–4 separately approved installed cores | **No weight updates**; differences and reproducibility |
| `fit-emulator-world-model` | Validates original policy plus source report, episode-grouped holdout, then performs real minibatch AdamW | **Actual local neural candidate parameter updates when run**; never Jeeves production transformer changes |

### A. Controlled experiment matrix: one emulator, many hypotheses

Start with an original owned ROM:

```bash
python -m skeleton.jeeves.game_learning_cli build-dmg \
  --seed 42 --title "Original Training World" \
  --output /private/roms/original-training-world.gb
```

Measure exact-state interventions in the experimental Game Boy interpreter:

```bash
python -m skeleton.jeeves.game_learning_cli experiment-emulator \
  --target game_boy \
  --rom /private/roms/original-training-world.gb \
  --rights-acknowledged --seed 42 \
  --episode-steps 32 --anchors 3 --repeats 2 \
  --longest-duration 4 --max-native-steps 1536 \
  --evidence-file /private/research/controlled-interactions.json
```

The baseline, sustained, single pulse, delayed, alternating, recovery, A→B
and B→A input sequences are executed from exactly the same verified savestate
for each anchor. Repetitions must agree before the effect is called repeatable.
The last state is measured using actual next-observation feature values,
native frame digests, native step returns and native savestate hashes.

For a fully approved installed native libretro core, use
`--target emulator:game_boy --core gambatte` and an explicitly admitted
single-file private ROM. Native-only additional trials include combined
button chords, keyboard chords and real multiport input controls.

**Memory telemetry:** separately opt into up to eight named, bounded native
regions with an explicit operator-authored JSON file:

```json
{
  "watches": [
    {"name": "operator-chosen-ram-page", "region": 2, "offset": 0, "size": 16}
  ]
}
```

Pass `--memory-watch-file /private/research/watches.json` only when the
specific installed core exposes that libretro memory region. The collector
records **byte-count changes and SHA-256 before/after**, not raw memory bytes.
It does not assert which address represents health, ammunition, position,
cutscene state, weapons, item ownership, NPC interactions or victory.
Interpretation requires independent game-specific knowledge and verification.

Native trials that report visual motion while controls are indistinguishable
from passive input can be marked *cutscene-like*, never a verified cutscene:
menus, video playback, loading, NPC animation and unmapped inputs can create
the same numerical pattern.

### B. Comparisons between independent emulator cores

For two independently built, installed and operator-approved cores that
accept the **same** original, rights-cleared Game Boy ROM:

```bash
python -m skeleton.jeeves.game_learning_cli compare-emulator-cores \
  --target emulator:game_boy \
  --core gambatte --core sameboy \
  --rom /private/roms/original-training-world.gb \
  --rights-acknowledged --episode-steps 32 \
  --comparison-steps 16 --repetitions 2 \
  --max-native-steps 256 \
  --evidence-file /private/research/core-consistency.json
```

The comparison binds immutable game media identity, console target, approved
core identity and library SHA. Each emulator executes the same real action
sequence independently. Repeat stability is measured per core, while
cross-core differences are reported per native frame digest, normalized
sensor and actual visual-change reward.

**Different cores must never share native savestates.** Agreement does
not establish hardware accuracy; divergence does not by itself establish
which emulator is correct. An absent or unapproved binary fails explicitly.

### C. Adaptive learning curriculum: 10 views, then evidence-based revisits

The deep ROM Q training command now has 10 mandatory angles, followed by
a source-executed, UCB-style curriculum prioritizing real replay-verified
state novelty and action-contrast evidence. Underobserved actual actions
receive explicit exploration. Every decision and evidence update has a
source-bound digest; held-out evaluation runs never enter this scheduling
decision.

The **10-run plateau check requires both** no new coarse actual
frame/observation signatures and no newly visited Q state or Q-value
movement exceeding `1e-6`. This is evidence of a *local measured
plateau*, **not** mathematical learning exhaustion. Large run budgets can
end without saturation and must be labeled as budget exhaustion.

Past runs are retained in a finite reservoir with seeded randomized
boomerang intervals, reexecuted in fresh owned environments from actual
starting savestates. No rescan is counted as another Q update.

### D. Actually fit a candidate neural transition model

First execute `train-emulator-deep` as documented in the prior lab
guide and retain the policy file and its **matching evidence file**. The
CLI now saves independent checksums on both the policy and evidence so
the neural trainer can reconstruct and validate the original report.

Then perform real local, bounded numerical optimization:

```bash
python -m skeleton.jeeves.game_learning_cli fit-emulator-world-model \
  --policy-file /private/research/rom-policy.json \
  --evidence-file /private/research/rom-evidence.json \
  --model-file /private/research/rom-world-model-candidate.json \
  --training-report-file /private/research/rom-world-training.json \
  --width 20 --epochs 8 --minibatch 16 \
  --learning-rate 0.003 --max-samples 2048 --seed 42
```

**What the real optimizer does:**

1. Reconstitutes the precise parent report from the separate policy and
   evidence JSON files; verifies SHA-256 integrity, rights assertion,
   original run receipts, exactly ten passed scrutiny controls and
   all committed episode/transition identities.
2. Requires actual action/next-observation/reward tuples from the previously
   measured emulator training, never samples from the native policy's
   held-out evaluator.
3. Partitions entire **source episode groups** into train and held-out
   examples using deterministic SHA-based seed separation. No transition
   from a held-out episode participates in weight optimization or feature
   scaling.
4. Fits input normalization on train-only examples; encodes exact finite
   controller actions as a one-hot vector.
5. Runs an actual two-hidden-layer tanh neural forward/backward pass,
   minibatch AdamW updates, global gradient clipping, finite parameter
   guards and explicit optimizer-step counters. No PyTorch, GPU, network
   service or background worker is required.
6. Predicts a vector of next-observation **deltas** plus one-step measured
   environmental reward. This is a limited predictive world model,
   **not** an instruction-following transformer.
7. Compares candidate held-out mean square prediction error against a
   training-derived constant predictor, records every fixed training epoch,
   and gates candidate status on finite, measured improvement. Held-out
   observations are never gradients or normalization statistics.
8. Writes a new digest-identified **candidate-only** model plus report.
   Inference from it is marked explicitly speculative until actual
   emulator execution confirms the proposed transition.

Only the new world-model candidate receives local trained parameters. No
method mutates production Jeeves weights, reconfigures the active provider,
updates hyperweights, or asserts game mastery. Actual measured emulator
gameplay improvement requires separate long-horizon evaluation.

## Operational ceilings and acceptance

- Native sensor feature vector: **24 real channels**, of which 12 describe
  sampled temporal frame motion or audio changes. No claims of semantic
  image/audio recognition.
- Experimental state anchors: at most 8; repeated trials: 2–5; total
  native experimental step budget up to 8192.
- Cross-core comparison: 2–4 independently approved native cores;
  2–4 repetitions; up to 64 requested action steps.
- Q training: at most 256 source sessions and 8192 bounded main
  training transitions, with additional checkpoint replay/probe costs.
- Local neural candidate optimizer: 4–64 hidden units, 1–40 epochs,
  minibatches 1–64, up to 8192 admitted samples (default 2048).
- Outputs are private local file paths. No automatically collected third-party
  ROMs, keys or BIOS; source rights remain an explicit responsibility of
  the operator.

The following remain unverified and block any release claim: a clean
native build/approval, original ROM boot and forward/reverse replay on
hardware-comparable cores, repeatable actual native multiport experiments,
source-identity and licensing review, focused regression/test execution,
CI signoff, real optimization-run receipt, held-out accuracy improvement,
and independent proof of increased game skill.


## E. Physically verified multi-step world-model planning

After fitting a neural candidate and obtaining a **measured** held-out
predictive gain, the proposed planner may search a bounded tree of speculative
action sequences. Those proposals never update a policy or count as a real
game success. Each candidate plan must be executed repeatedly on the **actual
source ROM** from an identical restored native state, paired with a neutral
input sequence of the same length. Mismatched source/model identities and
early-terminated/shortened runs cannot be counted as positive evidence.

```bash
python -m skeleton.jeeves.game_learning_cli plan-emulator \
  --target game_boy --rom /private/roms/original-training-world.gb \
  --model-file /private/research/rom-world-model-candidate.json \
  --training-report-file /private/research/rom-world-training.json \
  --evidence-file /private/research/physical-plan-validation.json \
  --rights-acknowledged --episode-steps 32 \
  --anchors 2 --horizon 4 --beam-width 8 --proposal-count 3 \
  --repeats 2 --max-actual-steps 512
```

Search width is bounded to 16, horizon to 8 steps, and proposals to 6 per
actual initial state. Objectives are measured reward, visual activity, audio
activity (only if the original environment measures it), or low visual
activity. A positive source comparison is evidence only for the selected
**numeric objective**, never actual gameplay success or general AI capability.
A source-trained model that did not beat its held-out baseline is rejected
before it is permitted to propose a source-executed plan.

Physical planning also depends on a correct rewind of the host's *last raw
native audio chunk*, not only its framebuffer. The native host now binds
`audio_base64`, `audio_size` and `audio_sha256` into the checked savestate
and restores that previous audio telemetry before executing the next frame.
This closes an observation-history gap for temporal audio-onset features.
Host observations are cleared when a new episode is reset.

## F. Operator-authored game-objective experiments

Visual-change reward can be optimized by flashing screens, so it is not
adequate evidence of story progression, ability use, quest completion or
game mastery. The native-only operator-goal laboratory permits **explicit,
bounded actual libretro memory measurements**. Operators must provide the
source-rights assertion, hypothesis provenance, memory region/offset/width,
threshold/bitmask and an action sequence to test. No memory addresses,
score meanings or victory flags are guessed.

Example private `/private/research/operator-goals.json` file:

```json
{
  "source_authority": "Owned original ROM; operator mapped this game register",
  "goals": [
    {
      "label": "operator-claimed-objective-counter",
      "region": 0,
      "offset": 8192,
      "bytes_per_value": 2,
      "direction": "increase",
      "threshold": 1,
      "mask": 0,
      "signed": false
    }
  ],
  "interventions": {
    "press-a": ["a"],
    "press-a-right": ["a_right"],
    "press-a-twice": ["a", "a"]
  }
}
```

Use an actual approved core with lawful private media, for example:

```bash
python -m skeleton.jeeves.game_learning_cli probe-emulator-goals \
  --target emulator:game_boy --core gambatte \
  --rom /private/roms/original-training-world.gb \
  --goal-file /private/research/operator-goals.json \
  --evidence-file /private/research/operator-goal-measurements.json \
  --rights-acknowledged --episode-steps 32 \
  --anchors 2 --repeats 2 --horizon 6 --max-actual-steps 2048
```

Each active input sequence is padded with neutral controls to the same
length as the neutral baseline. Trials repeatedly restore the *same real
emulator state*. The collector returns the measured native memory bytes'
SHA-256, operator-selected bounded decoded values, controlled predicate
changes, actual frame/step identities and run-level repeatability. A source
state at which both active and neutral controls reach the threshold is not
reported as an active-only result.

**Critical qualification:** Even reproducible register changes do not by
themselves establish that the register represents score, health, inventory,
abilities, quests, NPC behavior, camera angle, cinematic state or a win. A
human-provided hypothesis must be corroborated by separate game-specific
evidence; no gameplay semantics are automatically certified. No commercial
ROMs/BIOS are included and no production weights are trained by this probe.

## Execution and proof status

The new `plan-emulator` and `probe-emulator-goals` paths, their governed
Jeeves mirrors, and synthetic regression cases are committed as source.
Actual local native ROM execution, Python regression runs, release CI,
per-core accuracy, learned gameplay improvement and production model
promotion are **not yet verified**. Operator-run source evidence must precede
any claim that the corresponding hardware features work.
