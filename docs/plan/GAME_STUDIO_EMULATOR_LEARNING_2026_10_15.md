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

## Canonical application routing

The existing authenticated `backend/core/game_learning.py` workspace now
recognizes the exact `game/studio/session.json` project file, rejects
ambiguous engine roots, resolves `studio:<editor>` from the strictly
validated source rather than a fictional console ID, and advertises registered
studio engines through the existing catalog response. Normal project
simulation, human demonstration, local policy jobs, parallel actors and studio
campaigns can resolve the engine through the existing workspace authority.
Episode replay depth is limited to 128 even where a generic job asks for more.

This does **not** create a second ungoverned API or skip tenant/project/source
authority. Frontend integration and exact-head application tests remain
necessary before release.

## Real Jeeves neural candidate from replay-verified engine experience

An additional bridge, `skeleton/ai/training/jeeves_studio_curriculum.py`,
collects actual original-game state transitions into a training-only corpus.
Each episode is independently re-executed, with bounded action, seed,
engine source and SHA256 identity. On checkpoint training, untrusted serialized
claims are rejected, and the corpus is replay-verified a second time.

```bash
python -m skeleton.ai.training.jeeves_studio_curriculum \
  --engine economy --actions inspect survey wait --seed 9 \
  --output /private/engine-corpus.json --authorized --rights-cleared
sha256sum /private/engine-corpus.json
python -m skeleton.ai.training.jeeves_production_game_session \
  --run-id game-corpus-01 --attestation /private/attestation.json \
  --output-directory /private/new-candidate-folder \
  --studio-corpus /private/engine-corpus.json \
  --studio-corpus-expected-sha256 <independently-verified-64-hex-sha>
```

The checkpoint trainer must still have a real independently pinned
`SKELETON_OWN` model, does actual optimizer updates only on a **candidate**,
and independently evaluates its held-out outputs. This does not automatically
train or promote live production weights, or prove improved game design.

## Create a game-engine project directly in Jeeves's learning workspace

The existing authenticated learning application now admits `console_id=
"studio:economy"` (and every registered original-game engine) in the
regular create-project route. It builds the actual default
`game/studio/session.json` from the canonical editor schema, not a fake
console profile. Native/libretro paths are unchanged. The normal project
get/simulate/record/train and replay-fenced source writes retain the tenant
and rights boundaries. Source types cannot be silently swapped across two
authoritative engines. The existing React Native learning-workspace console
picker now shows searchable **Original game** engine options from the same
backend catalogue. No parallel ungoverned API or fake hardware renderer was
introduced.

## Replay-linked measured game-state telemetry frame

`skeleton/jeeves/game_studio_frame.py` generates a deterministic 96x64 RGB24
status visualization from the actual source-executed per-step observation and
session receipt. `StudioGameEnvironment.preview()` exposes it through the
existing emulator-compatible `pixels_base64 / width / height / format`
frame contract without a second API, and carries a SHA-256 digest, explicit
state metric labels, and a source session digest. The existing frontend
recognizes `render_kind="reference_state_telemetry_raster"` and labels the
frame as telemetry, never as actual engine-world pixels or audio.

This is a visual monitor for learning mechanics, not a game renderer. Native
emulator RGB remains bound to the approved actual libretro framebuffer.

## AI-proposed rules and multi-circumstance model learning

`skeleton/jeeves/game_studio_rule_curriculum.py` is a pure, bounded
`rule_authoring_contract(source)` and `apply_rule_proposal(source, proposal)`
gateway. Jeeves may propose source-bound, non-executable typed data edits,
but never arbitrary Python, imported code, unknown model knobs, player
inventory, victory, identity, source ownership or policy promotion. The
existing editor and authored-scene normalization revalidates every change.
A proposal is pinned to a SHA-256 digest of the original canonical game
source; a stale model suggestion cannot mutate another engine version.

Admitted edit operations: `set` existing typed value, `add` or
`multiply` bounded integer settings, `toggle` existing boolean, or
one source-bound scalar leaf in an authored layout. At most 12 edits per
proposal and seven variants per curriculum are admitted. Layout edits
cannot create new objects, change IDs, add script/URL fields, bypass
original-only constraints, or silently reuse a scene under incompatible
settings. For engines without authored scenes, only settings variation is
available.

**Example rule batch for the default economy engine.** Generate the parent
SHA-256 from a canonical source through the `rule_authoring_contract`
helper, rather than typing or guessing it:

```json
{
  "schema_version": "skeleton.game_builder.ai_rule_batch.v1",
  "proposals": [
    {
      "schema_version": "skeleton.game_builder.ai_rule_proposal.v1",
      "proposal_id": "high-price-volatility",
      "base_digest": "<actual hash returned by rule_authoring_contract>",
      "reason": "Challenge the economic policy with more elastic market prices.",
      "scene_seed": null,
      "operations": [
        {"scope": "settings", "path": "price_elasticity", "op": "add", "value": 3},
        {"scope": "settings", "path": "trade_tax", "op": "add", "value": 5}
      ]
    }
  ]
}
```

After the source hash is inserted and the operator clears the source
training rights, the candidate-only CLI can use this reviewed proposal
JSON and the existing source instead of a new external provider:

```bash
python -m skeleton.jeeves.game_studio_rule_training_cli \
  --editor economy --proposals /private/ai-rule-batch.json \
  --episodes-per-scenario 4 --max-steps 24 --seed 23 \
  --output /private/new-rule-policy.json \
  --neural-corpus-output /private/new-rule-neural-corpus.json \
  --authorized --rights-cleared
```

The outcome contains a single policy conditioned on the actual scenario,
measured Q updates, baseline-vs-candidate returns for each circumstance
on disjoint held-out seeds, source and transition digests, and no
automatic production promotion.

`skeleton/ai/training/jeeves_studio_rule_corpus.py` replays one
actual policy-training trajectory per scenario, pins all distinct game
rules and scenario seeds, and generates bounded observed learning text.
`load_studio_curriculum` independently reconstructs that multi-source
corpus and checks the caller-supplied, independently obtained SHA-256.
The existing `jeeves_production_game_session` can then ingest the file
with its `--studio-corpus` and `--studio-corpus-expected-sha256` flags.
This **only** adds operator-admitted candidate neural-training data; the
compiled app must supply the real attested live checkpoint, run the optimizer
and independently evaluate generated outputs before any production promotion.

**Existing governed campaigns:** `skeleton/jeeves/game_studio_learning.py`
now advertises actual studio engine setting knobs to its deterministic
bandit search. It proposes schema-validated edits to the exact
`game/studio/session.json` source, runs candidate Q-training in the
existing campaign authority and compares real source-bound evaluations
against the champion and adversarial perturbations. Invalid changes are
recorded as rejected proposals. The bandit is *not* falsely represented
as another natural-language LLM inference call; separate AI-model text
proposals enter through the explicit declarative proposal contract.

Release gates remain pending: exact-head Python tests, worker/IPC
integration, runtime security checks, actual campaign trials, actual
neural optimizer run, independent domain benchmarks and engine/world quality.
No complete engine/app, hardware, audio, rendering or real-world
generalization quality claim follows merely from these registrations.
