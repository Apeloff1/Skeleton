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
      "offset": 0,
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


## Candidate neural checkpoint safety

`fit-emulator-world-model` now accepts
`--max-compute-units 50000000` (default). Before allocating optimizer
moments, the trainer estimates dense pure-Python work from the **actual
admitted train partition**, layer width, action/sensor dimensionality and
epoch budget. A run exceeding the configured maximum fails before the
first optimizer step. The maximum operator override is 300 million estimated
units, not an unbounded compute promise. A caller with an active cancellation
probe can stop between minibatches; cancellation must not be reported as a
finished model.

The speculative inference path also **validates imported checkpoint tensor
shapes**, 4–64 hidden units, source observation/action labels, finite weights,
normalization coefficients, exact parameter count and training provenance.
A rehashed but malformed candidate JSON is not treated as a valid neural
model. These checks prevent obvious structural abuse; a self-computed hash
is not a cryptographic source authorization, and every actual source
hypothesis still needs independent game/core execution.

Focused regression sources cover altered savestate audio, source planning
versus neutral controls, rehashed malformed neural tensors, optimizer CPU
limits, finite cancellation, and operator-authored native memory hypotheses.
They have not been executed in this authoring session.


## G. One-command original ROM → Q replay → neural optimizer acceptance

The new explicit operator runner `scripts/accept_original_rom_ai_pipeline.py`
creates a lawful **original homebrew cartridge** from the repository's own
DMG game generator. It executes real Game Boy CPU instructions through
the experimental DMG interpreter, source-replays actual savestate action
sequences, trains the existing tabular Q policy on those replay-verified
transitions, validates each numeric neural example against its **original
per-transition replay receipt**, and performs **real bounded numerical
neural candidate optimization** with an independent episode-group holdout.

No external game ROM, BIOS, proprietary video/audio, installed core, cloud
LLM or provider connection is needed. To run a local acceptance session:

```bash
python scripts/accept_original_rom_ai_pipeline.py \
  --output-directory /private/research/original-rom-run-001 \
  --seed 42 --max-runs 12 --episode-steps 12 \
  --neural-epochs 4 --neural-width 8
```

The requested directory must not exist and its parent must already exist.
The operator writes create-only private `original-training.gb`,
`rom-policy.json`, `rom-source-evidence.json`,
`neural-world-candidate.json`, `neural-world-measurements.json`
and a final `acceptance.json`. The final acceptance record includes
independently measured CPU action/Q updates, neural optimizer steps, exact
source and model digests, and the candidate's held-out mean-square
prediction improvement relative to the original train-only baseline.

A measured training run that **does not** beat its held-out baseline returns
a nonzero exit code with the explicit status
`original_rom_trained_but_heldout_gain_not_proven`; simply running gradient
steps never proves capability. The receipt explicitly says native libretro
or physical hardware compatibility is unverified, and production Jeeves
transformer weights are never changed.

The typed per-transition source projection ties every neural training
example's action, observation, next observation, numeric reward, reward
components, and terminal flags to the original replay-audited episode receipt.
A changed candidate row cannot be admitted merely by recomputing the
candidate export's checksum without corresponding recorded source evidence.
This is an integrity consistency check, not a third-party cryptographic
attestation of untrusted source data.

## H. Original cartridge game-objective training from actual CPU memory

A separate `game_original_rom_goal_training.py` path probes the repo's
**specific authored original maze cartridge**, where the game generator
itself declares which CPU memory locations represent player X/Y, score,
and completion. It boots the emitted ROM to materialize the game's
**actual CPU-written VRAM tilemap**, derives a legal route through that map,
and then **physically executes controller inputs in the ROM interpreter**.

The action is not credited until the actual CPU game RAM commits the
expected adjacent position. On completion, score and objective-complete
registers must prove the authored state change. The operator then:

- Rewinds the exact initial CPU/memory/raster savestate and replays every
  recorded action; rewards, raw CPU observation evidence, frame digests
  and final snapshot must agree.
- Executes a matching-length neutral-input baseline from the identical
  starting savestate; idle frames must not achieve the same score/completion.
- Builds a separate bounded tabular Q-policy whose reward is tied to
  physically measured moves and the **source-authored** completion flag.

Use only the built-in homebrew generator, not another game ROM:

```bash
python -m skeleton.jeeves.game_original_rom_goal_training \
  --seed 42 --max-steps 2048 --max-frames-per-tile 16 \
  --evidence-file /private/research/original-goal-q-001.json
```

This is a narrowly scoped original-game demonstration, **not** a generic
automated health/score/quest detector or a guarantee of arbitrary cartridge
success. The resulting offline Q snapshot is a candidate from one measured
successful route; generalization, independent gameplay performance, hardware
accuracy, commercial IP compatibility, and production weight promotion
remain completely separate obligations.

**Verification status:** The new commands, manifest constraints and their
focused positive/negative regression sources have been committed to the
draft branch. No actual command or native session has been run from this
conversation's environment; successful completion and held-out gain require
real executable receipts.


## I. One manual acceptance suite: DMG cartridges, replay, Q, neural and goal

The new `scripts/run_game_rom_acceptance_suite.py` is an **executable
integrator** rather than another static catalog. The operator can run all
of the original-game proofs under one private, new output directory:

```bash
python scripts/run_game_rom_acceptance_suite.py \
  --output-directory /private/research/rom-ai-suite-001 \
  --seed 42 --process-timeout-seconds 600
```

Each source-executed phase retains a bounded create-only
`phase_*.json` result, including a failing process's exit code or
timeout and limited stdout/stderr. No final passing
`suite-acceptance.json` exists if **any** phase fails or any expected
original-ROM artifact/report SHA256 disagrees.

The suite gates these independent actual-operation sources:

1. Focused synthetic and original ROM regression modules (unless explicitly
   skipped with `--without-tests`; skipping never skips the actual bus/Q/
   neural/goal measurements).
2. `scripts/audit_original_gameboy_mapper_matrix.py` executes **five
   synthetic cartridge bus profiles** on the actual built-in ROM interpreter,
   proving bank address decode, SRAM controls, and CPU/memory/raster snapshot
   restore for ROM-only, MBC1, MBC2, RTC-free MBC3 and non-rumble MBC5.
3. `scripts/accept_original_rom_ai_pipeline.py` generates an entirely
   original ROM and measures source-replayed Q-learning and a separate
   CPU-trained neural world-model candidate with independently grouped
   heldout prediction error.
4. `skeleton.jeeves.game_original_rom_goal_training` executes the
   original generated maze, measures source-declared score/completion RAM,
   reverse-replays every action, checks a same-length idle baseline, and
   commits a bounded source-goal Q policy.
5. Read back the **actual privately written artifacts**, validate per-file
   SHA256 and source/weight/report links, compare true update counts and
   independently distinguish an accepted original-game goal from
   a hardware-accuracy, libretro, or production-model claim.

The new `.github/workflows/on-demand-rom-ai-acceptance.yml` exposes the
same path for an intentionally **manual-only** GitHub Actions dispatch,
after the workflow is present on the repository default branch. It has
`workflow_dispatch` only, read-only contents permissions, serialized
source-ref concurrency, an exact 35-minute job budget and a short-lived
receipt artifact containing both success and failure diagnostics.
**No push, pull-request, schedule, or merge trigger** is added; this does
not increase normal merge queue traffic. The optional workflow will not
run merely because this draft PR exists, and has not been dispatched.

### MBC2 is genuine new cartridge interpreter behavior

Unlike catalog declarations, the bounded built-in interpreter now
implements cartridge hardware types `0x05` and `0x06`:

- Up to 16 ROM banks (256 KiB), with zero selecting ROM bank one.
- 512 bytes of internal **four-bit** save RAM, not a fictitious 8 KiB
  external SRAM bank. Reads expose a high nibble of `0xF`; writes retain
  only the low four data bits.
- Correct address-bit A8 qualification: RAM-enable writes at A8=0 in
  `0000–1FFF`, bank-select writes at A8=1 in `2000–3FFF`.
- Internal RAM addresses mirror across `A000–BFFF`, and disallowed
  high-nibble state payloads or invalid MBC2 RAM geometry are refused.
- Source-owned synthetic ROM regressions check A8 gate/no-op behavior,
  mirroring, SRAM disable, bank selection and exact savestate rollback.

The MBC2 work does **not** implement DMG boot ROM, APU audio, color-only
titles, cartridge real-time clocks, camera/motion sensors, cycle-perfect
PPU/timer behavior or arbitrary game compatibility. Source code and
synthetic specifications still require an actual acceptance run before
calling this hardware profile operational.

**Current proof limitation:** the workspace executing this chat cannot
resolve GitHub for a local clone. The source changes, test code and the
manual-only workflow are committed on PR #3935, but the suite, source
mapper matrix, native emulator builds and neural optimizer have not been
executed here. A source-authored receipt must precede any statement that
these gates pass.


## J. Virtual-clock MBC3 cartridge extension and source audit

The experimental DMG interpreter now admits **RTC-enabled MBC3 cartridge
types 0x0F and 0x10** in addition to the RTC-free types. This is a genuine
source CPU memory-bus feature: writes to 0x4000–0x5FFF select either cartridge
RAM or one of five virtual RTC registers (0x08–0x0C), and writes to
0x6000–0x7FFF explicitly latch the clock on a 0x00→0x01 sequence.

The virtual seconds, minutes, hours, 9-bit day counter, halt flag, and
sticky day-overflow carry are advanced in constant time from **4,194,304
emulated CPU cycles per virtual second**. No wall-clock timestamp, RTC
battery hardware, host clock catch-up after process shutdown, or accelerated
standby time is inferred. A halt keeps counters still; an operator clock
write can intentionally clear the carry bit. Values outside supported
clock register ranges fail closed instead of becoming fabricated evidence.

Savestates for timer-equipped cartridges use **machine snapshot schema v2**
with live registers, latched registers, previous latch bit, and fractional
cycle remainder. The ordinary RTC-free cartridges retain schema v1.
Snapshots are checked for valid elapsed-cycle remainder and clock bounds;
replaying from the same state reconstructs the same virtual time. It does
not prove real-cartridge RTC oscillator precision.

The original cartridge audit now verifies **eight configurations across
five mapper families**:

- ROM-only; standard MBC1 extended-ROM and four-SRAM-bank variants;
  internal four-bit MBC2; RTC-free MBC3; MBC3 timer-only and timer-plus-RAM;
  and 512-bank MBC5.
- Standard MBC1 four-bank SRAM configurations are rejected when declared
  ROM sizes exceed 512 KiB: the high selector is needed for ROM extension
  in those physical layouts (excluding unsupported MBC1M rewiring).
- RTC-equipped audit profiles independently check live CPU-clock increments,
  stable latch readings, explicit latch renewal, halt/resume behavior, actual
  external SRAM availability, and snapshot round trips.

Synthetic tests in
`skeleton/testing/test_game_rom_virtual_rtc.py` exercise the timer-only
header, latch protocol, fractional cycle replay, halt, 512-day rollover,
sticky carry and corrupt-state rejection. This testing source and its
manual acceptance integration are **committed, not executed in this chat**.

The manually dispatched suite still requires real execution and reports
only the supported interpreter experiments, never certified Game Boy
hardware timing, game-title compatibility or production AI weight promotion.


## K. Cycle-driven handheld timer and oscillator stop semantics

The experimental Game Boy CPU used by the ROM training laboratory now
models the timer as a falling-edge detector on the **internally selected DIV
bit**, rather than treating TIMA as an immediate reload counter. This
matters for source AI training because one mislabeled timer interrupt can
cause later actual RAM/PPU observations and reward traces to diverge.

- TAC frequency settings 00/01/10/11 sample divider bit 9/3/5/7.
- A DIV reset or TAC source/enable write causes a TIMA pulse only if it
  changes an enabled high timer signal to low. Timer control writes do not
  unconditionally increment the counter.
- TIMA overflow now holds 00 for four T-cycles, then copies current TMA
  and requests the IF timer bit. Writing TIMA during that pending interval
  cancels the pending reload; a TMA write affects the later load.
- Source CPU savestates include the **bounded pending timer phase**, which
  allows exact replay even when halted in the middle of a delayed overflow.
- The source interpreter's STOP opcode resets DIV and freezes the
  divider/TIMA/PPU clock until a controller event resumes the source CPU;
  HALT still advances CPU/peripheral timers.

These are **instruction-granular approximations** and explicitly do not
assert correct sub-instruction CPU memory bus phases, same-M-cycle TMA
transfer ordering, CGB speed switching, audio DIV side effects, timer
behavior during a full DMA blockade, or universal hardware correctness.
The timer state is not the independent MBC3 virtual cartridge RTC.
References: <https://gbdev.io/pandocs/Timer_and_Divider_Registers.html>.

The source test `skeleton/testing/test_game_rom_cpu_timer.py` covers
all four selected DIV bits, DIV/TAC glitches, four-cycle overflow, TIMA
cancellation, pending-cycle savestate replay, invalid phase rejection,
STOP oscillator freeze, and HALT continuation.

## L. Original CPU instruction-by-instruction multiview replay lab

The new `skeleton.jeeves.game_rom_instruction_divergence` laboratory
produces bounded, CPU-executed counterfactual evidence instead of relying
on visually inferred outcomes. It generates only the project's original
authored cartridge, boots the actual experimental LR35902 interpreter,
seals a **full source machine snapshot**, and then runs separately
controlled branches with exact independent replays:

```bash
python scripts/audit_original_rom_instruction_divergence.py \
  --evidence-file /private/research/original-source-divergence.json \
  --seed 42 --instruction-count 2048 \
  --sample-stride 8 --max-cycles-per-branch 131072 \
  --actions idle a right a_right
```

Up to eight distinct bounded input branches are allowed, including an
explicit idle control. Each branch executes a finite number of actual
CPU instructions, recording a source trace at regular instruction ordinals
with:

- PC before each sampled instruction, opcode byte, CPU registers/flags,
  actual schedule cycles, frame counter and pending interrupts.
- Exact DIV/TIMA/TMA/TAC/IE/IF and delayed-overflow phase, cartridge bank
  selector, cartridge RTC state where applicable.
- SHA-256 of **actual RAM, VRAM, OAM, I/O, SRAM and framebuffer** rather
  than a synthesised reward or screenshot-based guess.
- Only for this original generated maze, its authored player coordinates,
  score and completion registers; never inferred game labels for
  unrelated ROMs.
- Independent, exact re-execution of each controlled branch from the same
  full CPU/memory/frame/mapper snapshot. A differing repeated branch
  immediately fails, with no model update or pass receipt.
- The first distinct observed *instruction sample* compared against the
  identical-state passive control, broken into measured hardware domains.
  Equal instruction ordinals are not necessarily equal real-time duration
  when an instruction's cycle cost differs.

A new phase in the existing **manual-only**
`scripts/run_game_rom_acceptance_suite.py` refuses a complete source AI
acceptance result unless all source instruction traces and their nested
digests validate. It does not label a differing RAM or timer register as a
causal game win, a general skill gain, emulator compatibility, or neural
training. That interpretation must come from separate replayable
game-specific objectives.

The standalone source command and focused regression
`skeleton/testing/test_game_rom_instruction_divergence.py` are committed;
they have **not** been run during this authoring pass, and there is
no claim of observed emulator fidelity or production neural weight gain.


## M. Actual OAM sprite DMA timing as source-verified learning evidence

The experimental DMG ROM interpreter previously copied all 160 OAM sprite
attribute bytes immediately on a write to `FF46`. That fabricated an
impossible source timing relationship: later DMA data could appear to be
present at an earlier moment in a replayed game's framebuffer.

The current source implementation introduces a bounded CPU-cycle DMA engine:

- `FF46` source pages `00` through `DF` start a transfer. Pages whose
  bus behavior has not been modeled are **rejected** rather than assigned
  fictitious source values.
- The transfer has four startup T-cycles, then reads one byte from the
  actual cartridge/WRAM bus every four T-cycles, copying into `FE00–FE9F`
  (160 bytes). A later write to `FF46` can restart the source.
- Source reads take place at their actual simulated DMA transfer tick,
  rather than pre-sampling all source bytes when the transfer begins.
- Native interpreter savestates seal the source page, DMA active flag,
  copied-byte count, fractional four-cycle phase and startup remaining.
  Partial transfers can be rewound and completed with identical OAM
  contents, even when a snapshot falls between byte-copy ticks.
- The Game Boy PPU's scanline and STAT edge are now advanced on the **same
  individual T-cycle** as the divider and DMA. A scanline drawn earlier
  cannot observe future sprite bytes from the rest of an instruction.
- The original-ROM CPU counterfactual module records those real DMA fields
  plus a SHA256 digest of the current OAM, allowing AI source-evidence
  analysis to distinguish a memory-transfer effect from game-state effects.

The new focused source regression module
`skeleton/testing/test_game_rom_dma_timing.py` probes delayed start,
per-byte copy phase, no prefetch of changing ROM/RAM source bytes,
mid-transfer source restart, exact savestate recovery, STOP pause, invalid
source pages, and raster scanline ordering. It is included in the
**manual-only** original ROM AI acceptance suite.

The timing references are documented by
<https://gbdev.io/pandocs/OAM_DMA_Transfer.html>. **Known unsupported
hardware behavior remains significant**: DMG CPU bus restrictions during
DMA, exact OAM scan/pixel-fetch contention, unsupported upper bus pages,
CGB general-purpose/HDMA, LCD fetch pipeline cycle perfection, boot ROM
and sound chip. This is an intermediate fidelity upgrade, not full
hardware certification.

### Native cartridge first boot above 2 MiB

The independent approved-libretro first-boot operator gate now uses the
exact `MAX_CONTENT_BYTES` budget from the existing emulator catalog,
which is **16 MiB** for a single inline ROM, rather than an inconsistent
2 MiB cap. This enables actual source-first-boot auditing of larger
lawful cartridges, including some SNES and GBA homebrew titles.
Optical-disc, multi-file cue/bin, and large CHD content still need an
independent governed referenced-media route; they must not be force-loaded
as giant in-memory single-ROM blobs or claimed verified by this
cartridge-only check.

The code and synthetic regressions have been committed but **not executed
during authoring**. No new native core has a verified boot, no original
ROM training result is reported as measured, and no production Jeeves
model weights are updated by these changes.


## N. Bounded original-ROM temporal controller sequences and real CPU snapshots

The original homebrew ROM microtrace lab now supports not only a static
controller hold, but also up to **eight total independent control branches**
with a finite 2–8-phase instruction-timed schedule per temporal branch.
Every phase change is applied to the **same real LR35902 CPU from an exact
starting savestate** at a deterministic CPU instruction boundary. Every
branch is executed twice independently and the full source-result digests
must match.

```bash
python scripts/audit_original_rom_instruction_divergence.py \
  --evidence-file /private/research/source-cpu-sequence-001.json \
  --seed 42 --instruction-count 2048 --sample-stride 8 \
  --max-cycles-per-branch 131072 \
  --actions idle a right a_right \
  --sequence a,idle,right \
  --sequence right,a \
  --sequence a_right,idle
```

The source input journal records the exact **instruction ordinal** of
each controller assignment (for example 0, 682, 1365 for three phases
over 2048 instructions). It never replaces that ordinal with a guessed
frame time. Source model comparisons separately record real CPU cycle
counts; actions with different branch costs are not assumed to have equal
wall-time lengths. Repeated identical adjacent controller phases,
unadmitted buttons, duplicates and input schedules beyond the finite
branch budget fail before any CPU trial.

The same manual-only original ROM AI acceptance suite now tests these
three scheduled sequences in addition to four basic single-input branches.
It checks nested per-instruction sample digests, source intervention
journals, exact phase boundaries, repeated final CPU/memory states, and
the total instruction/assignment counters. A rehashed manifest with
missing or modified action-phase events cannot satisfy the suite.

This source evidence is useful for studying input order, control release,
simultaneous buttons, and time-dependent RAM/PPU/RTC/DMA effects. It does
**not** assert that the AI has learned those action consequences from
neural gradients or achieved a game objective. Learned policy improvement
still requires separate truly source-run training, qualified independent
evaluation, and explicit production promotion approval.

### Current execution and source-bound limitations

As of this draft authoring pass, the source additions include the OAM DMA
engine, coupled T-cycle timer/PPU/DMA progression, multi-action source
instruction trials, governed AI mirrors, and dedicated regression cases.
The local environment has no working GitHub clone and the GitHub
connector has no workflow-dispatch action. **No actual acceptance,
native emulator build, regression suite or neural optimization job has
been run.** An existing manual workflow is defined in source but is not
an executed result and the PR remains draft.


## O. Independent CPU instruction and arithmetic conformance before AI training

A replayed emulator can be *consistently wrong*. Its original-ROM
neural world model would still learn those invented CPU rules if the
only gate compared an instruction to a second execution of itself.
To avoid that self-validation failure, the original-ROM operator suite
now requires two separate executable source conformance stages.

**1. Original SM83 opcode coverage and independently sourced cycles**

The source-owned
`scripts/audit_original_gameboy_cpu_opcodes.py` runs a synthetic local
32-KiB Game Boy ROM for every legal single-step base operation and
every `CB`-prefixed variant. It checks the executed machine's CPU
register/instruction counters, T-cycles, and exact replay of the
CPU/memory/cartridge/PPU state from the same checkpoint.

A pinned `machine/gbdev_sm83_opcode_reference.json` contains **both
256 unprefixed and 256 prefixed opcode definitions**, including
documented instruction lengths, mnemonic, flags and the independent
community timing tables. It derives from
<https://github.com/gbdev/gb-opcodes/blob/376f61c86fdac2048f7ce5fe838ae756b306017e/Opcodes.json>
under **CC0-1.0**. The oracle resolves taken versus not-taken
conditional branch cycles from actual pre-instruction Z/C flags.
It fails if a documented legal operation has the wrong T-cycle count,
an invalid opcode executes, a reference input is malformed or a
restored execution produces a different CPU/memory/raster state.

The scope is deliberately specific: 244 non-CB base opcodes plus
256 CB variants are executed individually and each replayed again
(1,000 actual instruction executions). The prefix dispatcher makes
245 total legal base identities; all 11 undefined unprefixed opcodes
must instead fail. The count is **not 1,000 distinct opcodes**.

```bash
python scripts/audit_original_gameboy_cpu_opcodes.py \
  --evidence-file /private/research/sm83-opcodes.json
```

**2. Independent Z/N/H/C arithmetic reference**

`scripts/audit_original_gameboy_alu_flags.py` performs **5,184
separate real source ALU operations**, across 18 small, half-carry,
sign-boundary and byte-overflow accumulator/operand values, both
carry-in states and all eight arithmetic/logic families:
ADD, ADC, SUB, SBC, AND, XOR, OR and CP. A separately calculated
reference computes the expected A register and zero, subtract,
half-carry and carry flags; it refuses the first differing measured
operation. This is a bounded boundary corpus, not exhaustive
65,536×2 testing of every arithmetic input.

```bash
python scripts/audit_original_gameboy_alu_flags.py \
  --evidence-file /private/research/sm83-arithmetic.json
```

`skeleton/testing/test_game_original_cpu_conformance.py` exercises
both real sources and adversarially tampers with a rehashed opcode
receipt, and separately replaces an ALU execution with a no-op to
verify that the independent oracle fails. The manual-only
`scripts/run_game_rom_acceptance_suite.py` now *requires* both
source reports before its final training acceptance receipt.
All source reports are finite, hash-bound and marked **not hardware
accuracy certification**.

This **does not** prove correct mid-instruction memory access cycles,
full OAM DMA CPU lockout, LCD dot-level pixel fetching, electrical
DMG timing, all operand combinations, audio/speed modes or universal
game compatibility. Nor does a completed source CPU matrix train
Jeeves production transformer parameters; separate actual
gradient execution and independently held-out downstream outcomes
remain mandatory.

**Execution note:** The CC0 reference and implementation are committed
to draft PR #3935, but a local GitHub clone could not be resolved
from this session; no actual conformance command, emulator native
build, ROM boot, or gradient session has been executed here.
