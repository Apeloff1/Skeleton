# Emulator-compatible original-game policy learning

The canonical original-game advanced reference engines are not libretro
cores and cannot load ROMs. This adapter implements **the same learning
environment protocol** (`spec/reset/step/preview/snapshot/restore/close`)
used by the Jeeves emulator training system. It supplies actual state-derived
observations and replay-backed transitions for the existing
`GamePolicyLearner` and `ParallelGamePolicyTrainer`.

* Canonical execution: `skeleton/ai/game_builder/advanced_gameplay_runtime.py`
* Integration: `skeleton/jeeves/game_studio_environment.py`
* Existing learning: `skeleton/jeeves/game_learning.py`
* Existing actors: `skeleton/jeeves/game_learning_parallel.py`
* Candidate CLI: `skeleton/jeeves/game_studio_policy_cli.py`

Use `GameEnvironmentRequest(target_id="studio:economy",kind="studio",
tree=studio_request_tree(make_studio_source("economy")),max_steps=32)`.
This produces the same policy-spec objects and independently replayable
snapshots as the other built-in learning environments. All **33 registered
reference game engines** can now expose their mechanics through this interface.
The policy action set is an explicit subset of at most 32 actual game commands;
an episode supports at most 128 accepted or rejected turns. Unsupported
commands, foreign scenes and forged snapshots fail closed.

## Actual candidate training

With the original project's rights cleared and private writable output path:

```bash
python -m skeleton.jeeves.game_studio_policy_cli \
  --engine economy --episodes 8 --max-steps 32 \
  --actions inspect wait survey buy:1 sell:1 travel:1 \
  --output /private/new-studio-candidate.json \
  --authorized --rights-cleared
```

The tool executes original gameplay episodes, performs **real tabular Q-value
updates** and writes a new candidate policy checkpoint and trace digests.
It never overwrites active policy state, never edits the production Jeeves
transformer or claims equivalent neural-weight improvement. Professional
model-weight training remains separately checkpoint-pinned under
`skeleton/ai/training/jeeves_production_game_session.py`, where no
session-to-neural-dataset integration is claimed in this slice.

Rewards combine observed progress, score/wealth, health, actually earned
outcomes, rejected action penalties, and per-step cost. This is task-specific
local policy learning; results require independent evaluation before promotion.
Preview intentionally supplies state fields, not imaginary frames. Full native
emulator pixels/audio remain exclusive to the approved libretro runtime.

## Opt-in learning from actual gameplay

The same candidate CLI also accepts `--played-actions inspect survey wait`
with `--consent-ref operator-consent:demo-9`. It executes those controls
against the real replay-authoritative engine, records the typed episode using
`GameDemonstrationRecorder`, independently replays all commands with
`learn_demonstrations`, and only then applies the genuine Q updates and
an imitation prior. The final candidate includes the demonstration digest
and number of measured action-derived optimizer updates.

This action-learning path is explicitly consent and rights-gated. It cannot
accept an uploaded unchecked label as sufficient proof and cannot silently
write production neural weights.
