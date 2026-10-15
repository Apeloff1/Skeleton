# Deep native ROM emulator training — implementation and operator controls

**Status:** Source implemented, candidate only. No native core was built, no
ROM training job was launched, and no AI transformer weights were optimized
during this change. The implementation uses the existing real libretro worker
or experimental original DMG cartridge interpreter; it does not substitute a
game-shaped mock for unavailable emulators.

## How to run an actual rights-cleared local session

First create your own original Game Boy ROM:

```bash
python -m skeleton.jeeves.game_learning_cli build-dmg \
  --seed 42 --title "Training Garden" \
  --output /private/games/training-garden.gb
```

Then **explicitly acknowledge source rights** and choose three different
private output files:

```bash
python -m skeleton.jeeves.game_learning_cli train-emulator-deep \
  --target game_boy --rom /private/games/training-garden.gb \
  --rights-acknowledged --seed 42 \
  --max-runs 48 --episode-steps 24 --stagnation-runs 10 \
  --checkpoint-stride 6 --counterfactual-actions 3 \
  --boomerang-interval 5 --boomerang-retained 4 \
  --heldout-episodes 2 \
  --policy-file /private/research/rom-policy.json \
  --checkpoint-file /private/research/rom-checkpoint.json \
  --evidence-file /private/research/rom-evidence.json
```

For real native libretro, first compile/install/approve the requested exact
core, and point `SKL_GAME_EMULATOR_REGISTRY` at its operator registry.
Then select `--target emulator:game_boy --core gambatte` and pass a
rights-cleared local ROM. The native host requires its declared Linux,
bubblewrap and static ABI sandbox. The local request loader currently
accepts only single-file bounded uploads (up to 2 MiB at its serialized
environment request); larger CD/disc and multi-file packages use the
existing application-controlled streamed emulator-content adapter.

No command fetches game ROMs, commercial assets, encryption keys, or BIOS.
Rights acknowledgement is an **operator assertion**, not a legally verified
license receipt.

## What happens at each real training run

1. Resolve the exact approved emulator/content identity and create an isolated
   native runtime (or original DMG interpreter), then capture its source-bound
   initial state and observation.
2. Select action sequences with a ten-angle rotating policy: exploration,
   learned policy, adversarial/minimum-Q, temporal, boundary, recovery,
   randomized perturbation, causal/greedy, reversed controls and boomerang.
3. Capture real frame/audio data. The native libretro host now exposes
   twelve normalized measured channels: brightness, visual frame difference,
   audio RMS, time fraction, frame entropy, luminance contrast, spatial edge
   strength, color saturation, color bias, audio peak, zero crossings and
   left/right stereo difference. These **do not identify objects, music,
   abilities, score, win/loss or gameplay quality**.
4. At selected points, fork actual native states into alternative inputs and,
   for libretro, one- through four-controller combinations. Replay restores
   the original state before continuing. Such probes have no false Q action
   or reward update.
5. Run ten bounded scrutiny checks on source authority, action schema, exact
   trace digest, finite reward accounting, frame custody, and reverse replay.
   Each rewind checkpoint reexecutes its **actual emulator action suffix** and
   must reproduce the original final state digest.
6. Only after successful replay, pass the trace into the existing governed
   `GamePolicyLearner.train_offline` path to do **real tabular Q-value
   updates**. One verified state/action transition yields one counted update.
7. Preserve older starting snapshots with deterministic reservoir sampling;
   re-examine one randomly selected past run at randomized seeded intervals
   inside a newly built approved runtime. Re-evaluations are not falsely
   counted as extra successful learning episodes.
8. Stop only when ten consecutive executed runs add no new coarse
   frame-plus-observation signatures, or when the explicit resource/run budget
   is exhausted. Those signals measure *visual exploration saturation*,
   not mathematical impossibility of further learning or game mastery.
9. Evaluate the candidate on disjoint held-out episodes against the
   existing seeded random policy. Libretro cores do **not** share a universal
   reproducible RNG; measured held-out returns must therefore be interpreted
   as observational rather than device certification.
10. Write policy/checkpoint/evidence records locally; export numeric,
    exact-trace-bound source/action/reward examples as a **neural candidate
    dataset only**. No production neural optimizer, checkpoint mutation,
    network transfer, online self-modification or weight promotion runs.

The returned report separates a saturation exit from a bounded exit:
`visual_novelty_saturated` versus
`budget_exhausted_before_saturation`. Native runtime failure, missing
snapshot support, replay mismatch, wrong target, missing rights assertion,
inconsistent firmware or interrupted worker are errors and **do not
silently downgrade to reference simulations**.

## Quantitative resource limits

| Control | Maximum |
| --- | ---: |
| Main measured sessions | 256 |
| Steps per session | 128 |
| Training state/action transitions (one invocation) | 8,192 |
| Independent replay suffix checkpoints | up to one every step |
| Alternative actions at selected checkpoints | 8 |
| Older retained savestates for boomerang replays | 8 |
| Held-out evaluation episodes | 8 |
| Actual framebuffer samples per frame | 4,096 |
| Actual stereo samples per audio analysis | 4,096 pairs |

Each physical native episode can still execute additional actual emulator
steps for counterfactuals, reverse auditing, boomerang returns and held-out
evaluation. The numeric `actual_training_steps` field counts only policy
training steps; separate receipt fields count replay/probe work.

**Remaining production gaps:** independent core compilation, hardware/OS
portability outside the existing Linux sandbox, representatively verified
native replay/state serialization, robust content/firmware integration,
game-specific causal reward recognition, human-authored success criteria,
per-era gameplay quality, and **actual** source-audited neural candidate
optimization + held-out improvement before any weights can be promoted.
This source change closes none of those by assertion.
